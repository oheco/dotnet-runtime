#!/usr/bin/env python3
"""Capture exact NuGet archives, or verify and stage an offline package feed.

Capture runs only after restore finishes. A captured cache is an input bundle,
not a claim that every package in it is part of the delivered SDK.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def capture(cache):
    entries = []
    for archive in sorted(cache.glob("*/*/*.nupkg")):
        with zipfile.ZipFile(archive) as package:
            names = [name for name in package.namelist() if name.endswith(".nuspec")]
            if len(names) != 1:
                raise ValueError(f"Expected one nuspec: {archive}")
            root = ET.fromstring(package.read(names[0]))
            for node in root.iter():
                node.tag = node.tag.rsplit("}", 1)[-1]
            metadata = root.find("metadata")
            identifier = metadata.findtext("id")
            version = metadata.findtext("version")
            license_node = metadata.find("license")
            license_info = (dict(license_node.attrib, value=license_node.text or "")
                            if license_node is not None else
                            {"url": metadata.findtext("licenseUrl") or ""})
        source_metadata = archive.parent / ".nupkg.metadata"
        source = json.loads(source_metadata.read_text()).get("source", "") if source_metadata.exists() else ""
        parsed_source = urllib.parse.urlsplit(source)
        if parsed_source.username or parsed_source.password or parsed_source.query:
            raise ValueError(f"Refusing to record credentials or query in feed URL: {identifier}")
        entries.append({"id": identifier, "version": version,
                        "archive": archive.relative_to(cache).as_posix(),
                        "size": archive.stat().st_size, "sha256": digest(archive),
                        "source": source, "license": license_info})
    if not entries:
        raise ValueError("No NuGet archives found")
    return {"format": 1, "packages": entries}


def stage(cache, manifest, destination):
    destination.mkdir(parents=True, exist_ok=True)
    for item in manifest["packages"]:
        archive = (cache / item["archive"]).resolve()
        if not archive.is_relative_to(cache.resolve()):
            raise ValueError("Input archive path leaves cache")
        if archive.stat().st_size != item["size"] or digest(archive) != item["sha256"]:
            raise ValueError(f"NuGet archive checksum mismatch: {item['id']} {item['version']}")
        target = destination / archive.name
        if target.exists():
            if digest(target) != item["sha256"]:
                raise ValueError(f"Conflicting offline archive: {target}")
        else:
            shutil.copyfile(archive, target)
    configuration = ET.Element("configuration")
    sources = ET.SubElement(configuration, "packageSources")
    ET.SubElement(sources, "clear")
    ET.SubElement(sources, "add", key="fixed-offline-inputs", value=str(destination.resolve()))
    ET.indent(configuration)
    ET.ElementTree(configuration).write(destination / "NuGet.Config", encoding="utf-8", xml_declaration=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["capture", "stage"])
    parser.add_argument("cache", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    if args.action == "capture":
        manifest = capture(args.cache)
        args.manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    else:
        if args.destination is None:
            parser.error("stage requires --destination")
        manifest = json.loads(args.manifest.read_text())
        stage(args.cache, manifest, args.destination)
    print(f"{args.action}: {len(manifest['packages'])} fixed NuGet archives")


if __name__ == "__main__":
    main()
