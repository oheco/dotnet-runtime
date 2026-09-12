#!/usr/bin/env python3
"""Prepare the cross-build SDK subset directly from the fixed SDK archive."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import shutil
import stat
import zipfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("destination", type=Path)
args = parser.parse_args()
work = Path(__file__).resolve().parent
entry = next(a for a in json.loads((work / "base-inputs.json").read_text())["archives"]
             if a["name"] == "ohos-sdk-native")
archive = Path(os.environ.get("DOTNET_OHOS_DOWNLOADS", work / "downloads")) / entry["archive"]
with archive.open("rb") as file:
    if hashlib.file_digest(file, "sha256").hexdigest() != entry["sha256"]:
        raise SystemExit("SDK archive checksum mismatch")
destination = args.destination.resolve()
if destination.exists() and any(destination.iterdir()):
    raise SystemExit("Destination must be empty")
destination.mkdir(parents=True, exist_ok=True)
prefixes = {"native/sysroot/": "sysroot/", "native/llvm/lib/clang/": "clang/",
            "native/llvm/include/": "include/", "native/llvm/lib/aarch64-linux-ohos/": "aarch64-linux-ohos/"}
count = 0
with zipfile.ZipFile(archive) as source:
    for info in source.infolist():
        for prefix, replacement in prefixes.items():
            if not info.filename.startswith(prefix):
                continue
            relative = PurePosixPath(replacement + info.filename[len(prefix):])
            if relative.is_absolute() or ".." in relative.parts:
                raise SystemExit("Invalid SDK member path")
            path = destination / relative
            if info.is_dir():
                path.mkdir(parents=True, exist_ok=True)
                break
            path.parent.mkdir(parents=True, exist_ok=True)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                target = source.read(info).decode("utf-8")
                if Path(target).is_absolute() or not (path.parent / target).resolve().is_relative_to(destination):
                    raise SystemExit("SDK link leaves prepared toolchain")
                path.symlink_to(target)
            else:
                with source.open(info) as reader, path.open("xb") as writer:
                    shutil.copyfileobj(reader, writer)
                path.chmod((mode & 0o777) or 0o644)
            count += 1
            break
    (destination / "NOTICE.txt").write_bytes(source.read("native/NOTICE.txt"))
print(f"Prepared {count} SDK files from {entry['sha256']} in {destination}")
