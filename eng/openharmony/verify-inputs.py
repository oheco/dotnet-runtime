#!/usr/bin/env python3
"""Verify prepared immutable downloads without making network requests."""
import argparse
import hashlib
import json
import os
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("names", nargs="*", help="Manifest input names; default: all")
args = parser.parse_args()
work = Path(__file__).resolve().parent
downloads = Path(os.environ.get("DOTNET_OHOS_DOWNLOADS", work / "downloads"))
entries = json.loads((work / "base-inputs.json").read_text())["archives"]
unknown = set(args.names) - {entry["name"] for entry in entries}
if unknown:
    parser.error("Unknown inputs: " + ", ".join(sorted(unknown)))
for entry in entries:
    if args.names and entry["name"] not in args.names:
        continue
    archive = downloads / entry["archive"]
    if archive.stat().st_size != entry["size"]:
        raise SystemExit(f"Input size mismatch: {archive}")
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != entry["sha256"]:
        raise SystemExit(f"Input SHA-256 mismatch: {archive}")
    print(f"Verified {entry['archive']}: {digest}")
