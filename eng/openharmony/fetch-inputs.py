#!/usr/bin/env python3
"""Download only manifest-pinned base inputs through the configured proxy.

This is a preparation step, separate from the offline build. Existing archives
must match the manifest; unexpected contents are never silently replaced.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("names", nargs="*", help="Manifest names; default: all")
args = parser.parse_args()
work = Path(__file__).resolve().parent
downloads = Path(os.environ.get("DOTNET_OHOS_DOWNLOADS", work / "downloads"))
entries = json.loads((work / "base-inputs.json").read_text())["archives"]
unknown = set(args.names) - {item["name"] for item in entries}
if unknown:
    parser.error("Unknown inputs: " + ", ".join(sorted(unknown)))
proxy = os.environ.get("DOTNET_OHOS_PROXY", "socks5h://127.0.0.1:10808")
if not proxy:
    parser.error("DOTNET_OHOS_PROXY must specify a proxy")
downloads.mkdir(parents=True, exist_ok=True)
for item in entries:
    if args.names and item["name"] not in args.names:
        continue
    destination = downloads / item["archive"]
    if destination.name != item["archive"]:
        raise SystemExit("Invalid archive filename")
    partial = destination.with_name(destination.name + ".partial")
    check = destination
    if not destination.exists():
        subprocess.run(["curl", "--proxy", proxy, "--noproxy", "", "--fail",
                        "--location", "--silent", "--show-error", "--retry", "3",
                        "--connect-timeout", "20", "--max-time", "1800",
                        item["url"], "--output", str(partial)], check=True)
        check = partial
    with check.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if check.stat().st_size != item["size"] or digest != item["sha256"]:
        raise SystemExit("Fixed input integrity check failed: " + str(check))
    if check == partial:
        partial.rename(destination)
    print("Verified " + destination.name, flush=True)
