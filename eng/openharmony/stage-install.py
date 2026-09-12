#!/usr/bin/env python3
"""Stage a built runtime/SDK layout for signing, without changing its payloads.

Use package-tree.py only after native signing and acceptance. This copier avoids
directory metadata operations unsupported by the Linux/HarmonyOS shared mount.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("source", type=Path, help="Extracted runtime archive or SDK redist directory")
parser.add_argument("destination", type=Path, help="New shared installation directory")
parser.add_argument("--kind", choices=["runtime", "sdk"], required=True)
args = parser.parse_args()
source = args.source.resolve(strict=True)
destination = args.destination.resolve()
work = Path(__file__).resolve().parent
if destination.is_relative_to(source):
    parser.error("Destination must be outside the source tree")
if not (source / "dotnet").is_file() or not (source / "shared/Microsoft.NETCore.App").is_dir():
    parser.error("Source is not a complete dotnet installation")
if args.kind == "sdk" and not (source / "sdk/10.0.401").is_dir():
    parser.error("Missing .NET SDK 10.0.401")
destination.mkdir(parents=True, exist_ok=False)
count = 0
for entry in sorted(source.rglob("*")):
    relative = entry.relative_to(source)
    target = destination / relative
    if entry.is_symlink():
        resolved = entry.resolve(strict=True)
        if not resolved.is_relative_to(source):
            raise ValueError(f"Source symlink leaves installation: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(os.path.relpath(destination / resolved.relative_to(source), target.parent))
    elif entry.is_dir():
        target.mkdir(parents=True, exist_ok=True)
    elif entry.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(entry, target)
        count += 1
    else:
        raise ValueError(f"Unsupported source entry: {relative}")
launcher = "dotnet" if args.kind == "sdk" else "dotnet-runtime"
(destination / "bin").mkdir(exist_ok=True)
shutil.copyfile(work / "launch-dotnet.sh", destination / "bin" / launcher)
shutil.copyfile(work / f"install-{args.kind}.md", destination / "README.openharmony.md")
for notice in json.loads((work / "licenses.json").read_text()):
    if args.kind not in notice.get("kinds", ["runtime", "sdk"]):
        continue
    original = work / "licenses" / notice["file"]
    with original.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if original.stat().st_size != notice["size"] or digest != notice["sha256"]:
        raise ValueError(f"Dependency notice integrity check failed: {original.name}")
    (destination / "licenses").mkdir(exist_ok=True)
    shutil.copyfile(original, destination / "licenses" / original.name)
print(f"Staged {count} files and bin/{launcher}; native signing and acceptance are still required.")
