#!/usr/bin/env python3
"""Create an isolated SDK build feed, preferring target-built runtime packages.

The input bootstrap feed must already have been verified against its fixed input
manifest. This operation performs no downloads and records every copied archive.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
import xml.etree.ElementTree as ET
import zipfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--bootstrap-feed", type=Path, required=True)
parser.add_argument("--runtime-packages", type=Path, required=True)
parser.add_argument("--runtime-archive", type=Path, required=True,
                    help="Source-built combined dotnet host/framework tar.gz")
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--runtime-version", default="10.0.12")
args = parser.parse_args()

required = {
    "microsoft.netcore.app.ref",
    "microsoft.netcore.app.host.openharmony-arm64",
    "microsoft.netcore.app.runtime.openharmony-arm64",
    "microsoft.netcore.app.crossgen2.openharmony-arm64",
    "microsoft.netcore.app.runtime.nativeaot.openharmony-arm64",
    "runtime.openharmony-arm64.microsoft.dotnet.ilcompiler",
    "microsoft.dotnet.ilcompiler",
    "microsoft.net.illink.tasks",
    "microsoft.netcore.platforms",
}


def identity(path):
    with zipfile.ZipFile(path) as archive:
        specs = [name for name in archive.namelist() if name.endswith(".nuspec") and "/" not in name]
        if len(specs) != 1:
            raise ValueError(f"Expected one package manifest: {path}")
        root = ET.fromstring(archive.read(specs[0]))
    metadata = next(child for child in root if child.tag.split("}")[-1] == "metadata")
    fields = {child.tag.split("}")[-1]: child.text for child in metadata}
    return fields["id"].lower(), fields["version"].lower()


inputs = {}
for origin, folder in [("bootstrap", args.bootstrap_feed), ("runtime-source-build", args.runtime_packages)]:
    # Arcade also emits legacy .symbols.nupkg with the same nuspec identity.
    # Those belong to a symbol feed, not the SDK restore feed.
    files = sorted(path for path in folder.rglob("*.nupkg")
                   if not path.name.endswith(".symbols.nupkg"))
    if not files:
        raise SystemExit(f"No NuGet archives in {folder}")
    for source in files:
        key = identity(source)
        if origin == "runtime-source-build" and (key[0] not in required or key[1] != args.runtime_version):
            continue
        if key in inputs and inputs[key][0] == origin:
            # dotnet tool restore also caches an unversioned archive filename.
            # Accept that alias only when its payload is byte-for-byte identical.
            previous = inputs[key][1]
            with previous.open("rb") as stream:
                previous_hash = hashlib.file_digest(stream, "sha256").hexdigest()
            with source.open("rb") as stream:
                source_hash = hashlib.file_digest(stream, "sha256").hexdigest()
            if previous_hash != source_hash:
                raise SystemExit(f"Conflicting package {key} in {origin}")
            continue
        inputs[key] = origin, source

# This executable runs on the Linux build machine to precompile the SDK. It
# is separate from the OpenHarmony crossgen2 pack installed in the product.
work = Path(__file__).resolve().parent
tool_name = "microsoft.netcore.app.crossgen2.linux-arm64"
tool_input = next(item for item in json.loads((work / "base-inputs.json").read_text())["archives"]
                  if item["name"] == tool_name and item["version"] == args.runtime_version)
tool_archive = Path(os.environ.get("DOTNET_OHOS_DOWNLOADS", work / "downloads")) / tool_input["archive"]
with tool_archive.open("rb") as stream:
    tool_digest = hashlib.file_digest(stream, "sha256").hexdigest()
if tool_archive.stat().st_size != tool_input["size"] or tool_digest != tool_input["sha256"]:
    raise SystemExit("Linux crossgen2 input integrity check failed")
if identity(tool_archive) != (tool_name, args.runtime_version):
    raise SystemExit("Unexpected Linux crossgen2 package identity")
inputs[(tool_name, args.runtime_version)] = "fixed-linux-build-tool", tool_archive

missing = sorted(name for name in required
                 if inputs.get((name, args.runtime_version), (None,))[0] != "runtime-source-build")
if missing:
    raise SystemExit("Missing target-built packages: " + ", ".join(missing))

# The SDK restores packs from NuGet but takes its root muxer and shared
# framework from a separate runtime archive. Keep that input pinned as well.
with tarfile.open(args.runtime_archive, "r:gz") as archive:
    members = {item.name.removeprefix("./"): item for item in archive.getmembers()}
    for name in ["dotnet", "libc++_shared.so",
                 f"host/fxr/{args.runtime_version}/libhostfxr.so",
                 f"shared/Microsoft.NETCore.App/{args.runtime_version}/libcoreclr.so",
                 f"shared/Microsoft.NETCore.App/{args.runtime_version}/System.Private.CoreLib.dll"]:
        if name not in members or not members[name].isfile():
            raise SystemExit(f"Missing runtime archive file: {name}")
    with archive.extractfile(members["dotnet"]) as stream:
        header = stream.read(20)
    if header[:6] != b"\x7fELF\x02\x01" or int.from_bytes(header[18:20], "little") != 183:
        raise SystemExit("Runtime archive muxer is not ELF64 AArch64")
    with archive.extractfile(members[f"shared/Microsoft.NETCore.App/{args.runtime_version}/libcoreclr.so"]) as stream:
        coreclr_digest = hashlib.file_digest(stream, "sha256").hexdigest()

# SetupBootstrapLayout snapshots the binplaced runtime pack. If it runs before
# that pack is refreshed, compiler publish can silently embed an older CoreCLR.
for name in ["microsoft.netcore.app.runtime.openharmony-arm64",
             "microsoft.netcore.app.crossgen2.openharmony-arm64",
             "runtime.openharmony-arm64.microsoft.dotnet.ilcompiler"]:
    with zipfile.ZipFile(inputs[(name, args.runtime_version)][1]) as archive:
        coreclr_files = [entry for entry in archive.namelist() if entry.endswith("/libcoreclr.so")]
        if len(coreclr_files) != 1:
            raise SystemExit(f"Expected one CoreCLR in {name}")
        with archive.open(coreclr_files[0]) as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != coreclr_digest:
                raise SystemExit(f"Stale compiler/runtime CoreCLR in {name}; refresh bootstrap after runtime binplacing")

# Require a new directory so a previous cache or package cannot survive by accident.
args.output.mkdir(parents=True, exist_ok=False)
feed = args.output / "packages"
feed.mkdir()
records = []
for (package_id, version), (origin, source) in sorted(inputs.items()):
    filename = package_id + "." + version + ".nupkg"
    destination = feed / filename
    shutil.copyfile(source, destination)
    with destination.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    records.append(dict(id=package_id, version=version, origin=origin, archive=filename,
                        path="packages/" + filename, size=destination.stat().st_size, sha256=digest))

downloads = args.output / "downloads"
downloads.mkdir()
runtime_name = f"dotnet-runtime-{args.runtime_version}-openharmony-arm64.tar.gz"
runtime_destination = downloads / runtime_name
shutil.copyfile(args.runtime_archive, runtime_destination)
with runtime_destination.open("rb") as stream:
    runtime_digest = hashlib.file_digest(stream, "sha256").hexdigest()
records.append(dict(id="dotnet-runtime-archive", version=args.runtime_version,
                    origin="runtime-source-build", archive=runtime_name, path="downloads/" + runtime_name,
                    size=runtime_destination.stat().st_size, sha256=runtime_digest))

config = ET.Element("configuration")
sources = ET.SubElement(config, "packageSources")
ET.SubElement(sources, "clear")
ET.SubElement(sources, "add", key="fixed-local", value=str(feed.resolve()))
ET.indent(config)
ET.ElementTree(config).write(args.output / "NuGet.Config", encoding="utf-8", xml_declaration=True)
(args.output / "manifest.json").write_text(json.dumps(records, indent=2) + "\n")
print(f"Prepared {len(records)} archives; {len(required)} target-built packages override bootstrap inputs.")
