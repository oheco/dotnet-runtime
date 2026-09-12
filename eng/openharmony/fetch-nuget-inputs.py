#!/usr/bin/env python3
"""Fetch fixed upstream NuGet archives through a proxy, verifying every payload.

This is the online preparation step. The resulting cache can be passed to
nuget-inputs.py stage; source builds use only that verified local feed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.parse

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("manifest", type=Path)
parser.add_argument("cache", type=Path)
parser.add_argument("--jobs", type=int, default=4, choices=range(1, 17))
args = parser.parse_args()
root = args.cache.resolve()
root.mkdir(parents=True, exist_ok=True)
proxy = os.environ.get("DOTNET_OHOS_PROXY", "socks5h://127.0.0.1:10808")
if not proxy:
    parser.error("A proxy is required for input downloads")
curl = ["curl", "--proxy", proxy, "--noproxy", "", "--fail", "--location",
        "--silent", "--show-error", "--proto", "=https", "--proto-redir", "=https",
        "--connect-timeout", "20", "--max-time", "600", "--retry", "3"]


def https(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query:
        raise ValueError("Expected a public HTTPS NuGet endpoint")
    return url


def verified(path, record):
    if path.stat().st_size != record["size"]:
        raise ValueError("NuGet archive size mismatch: " + str(path))
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != record["sha256"]:
        raise ValueError("NuGet archive hash mismatch: " + str(path))


groups = {}
for record in json.loads(args.manifest.read_text())["packages"]:
    path = (root / record["archive"]).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Archive path leaves input cache")
    identity = (record["id"].lower(), record["version"].lower(), record["sha256"])
    groups.setdefault(identity, []).append((record, path))

# Resolve each needed feed once. Archive hashes fix the inputs even when NuGet
# moves its public content endpoints. Existing verified archives need no network.
bases = {}
for items in groups.values():
    if any(path.exists() for _, path in items):
        continue
    record = items[0][0]
    if record.get("url"):
        continue
    source = https(record["source"])
    if source not in bases:
        index = json.loads(subprocess.check_output(curl + [source]))
        resources = [r for r in index["resources"]
                     if str(r["@type"]).startswith("PackageBaseAddress/")]
        if not resources:
            raise ValueError("Feed has no package content endpoint: " + source)
        bases[source] = https(resources[0]["@id"]).rstrip("/")


def fetch(items):
    record, target = items[0]
    existing = [path for r, path in items if path.exists()]
    for r, path in items:
        if path.exists():
            verified(path, r)
    if existing:
        source = existing[0]
        downloaded = 0
    else:
        identifier = urllib.parse.quote(record["id"].lower(), safe="")
        version = urllib.parse.quote(record["version"].lower(), safe="")
        url = record.get("url") or f"{bases[record['source']]}/{identifier}/{version}/{identifier}.{version}.nupkg"
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".nuget-download-", dir=target.parent)
        os.close(descriptor)
        temporary = Path(temporary)
        try:
            subprocess.run(curl + ["--output", str(temporary), https(url)], check=True)
            verified(temporary, record)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        source = target
        downloaded = 1
    for r, path in items:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, path)
            verified(path, r)
    return downloaded


with ThreadPoolExecutor(max_workers=args.jobs) as pool:
    count = sum(pool.map(fetch, groups.values()))
print(f"Verified {len(groups)} fixed package versions; downloaded {count}")
