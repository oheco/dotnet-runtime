#!/usr/bin/env python3
"""Install fixed SDK build/test frameworks without replacing the .NET 10 host."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tarfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("sdk_root", type=Path)
args = parser.parse_args()
work = Path(__file__).resolve().parent
manifest = json.loads((work / "base-inputs.json").read_text())
sdk_root = args.sdk_root.resolve()
count = 0
for entry in manifest["archives"]:
    if entry["name"] != "dotnet-runtime-linux-arm64":
        continue
    archive = Path(os.environ.get("DOTNET_OHOS_DOWNLOADS", work / "downloads")) / entry["archive"]
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != entry["sha256"]:
            raise SystemExit("Tool runtime archive checksum mismatch: " + entry["version"])
    prefix = PurePosixPath("shared/Microsoft.NETCore.App") / entry["version"]
    with tarfile.open(archive, "r:gz") as source:
        for member in source:
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts:
                raise SystemExit("Invalid runtime archive member path")
            if not relative.is_relative_to(prefix) or member.isdir():
                continue
            if not member.isfile():
                raise SystemExit("Unexpected non-file tool framework member")
            target = sdk_root / relative
            if target.is_symlink() or not target.resolve().is_relative_to(sdk_root):
                raise SystemExit("Tool framework path leaves bootstrap root")
            with source.extractfile(member) as reader:
                data = reader.read()
            if target.exists():
                if target.read_bytes() != data:
                    raise SystemExit("Existing tool runtime differs from fixed input: " + str(target))
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as writer:
                    writer.write(data)
                target.chmod(member.mode & 0o777)
            count += 1
print(f"Prepared or verified {count} fixed framework files; .NET 10 host unchanged")
