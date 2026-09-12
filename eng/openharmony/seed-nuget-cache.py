#!/usr/bin/env python3
"""Populate an empty NuGet cache from a verified local feed before SDK resolution.

MSBuild resolves its own Arcade SDK before project RestoreConfigFile takes
effect. Seeding all fixed package versions keeps this bootstrap step offline.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("dotnet", type=Path)
parser.add_argument("manifest", type=Path)
parser.add_argument("feed", type=Path)
parser.add_argument("project_directory", type=Path)
parser.add_argument("log_file", type=Path)
args = parser.parse_args()
for name in ("NUGET_PACKAGES", "DOTNET_CLI_HOME"):
    if not os.environ.get(name):
        parser.error(f"Set {name} to an isolated directory")
cache = Path(os.environ["NUGET_PACKAGES"])
if cache.exists() and any(cache.iterdir()):
    parser.error("NUGET_PACKAGES must be empty")
if args.log_file.exists():
    parser.error("Use a new log file")
configuration = args.feed.resolve(strict=True) / "NuGet.Config"
if not configuration.is_file():
    parser.error("Missing local NuGet.Config; prepare and verify the feed first")
data = json.loads(args.manifest.read_text())
records = data["packages"] if isinstance(data, dict) else data
packages = {}
for record in records:
    relative = record.get("path", Path(record["archive"]).name)
    if not relative.endswith(".nupkg"):
        continue
    archive = (args.feed / relative).resolve(strict=True)
    if not archive.is_relative_to(args.feed.resolve()) or archive.stat().st_size != record["size"]:
        parser.error("Invalid package path/size: " + relative)
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != record["sha256"]:
        parser.error("Package hash mismatch: " + relative)
    packages.setdefault(record["id"].lower(), set()).add(record["version"])
if not packages:
    parser.error("Manifest contains no package identities")
project = ET.Element("Project", Sdk="Microsoft.NET.Sdk")
properties = ET.SubElement(project, "PropertyGroup")
for name, value in (("TargetFramework", "net10.0"),
                    ("DisableImplicitFrameworkReferences", "true"),
                    ("NuGetAudit", "false")):
    ET.SubElement(properties, name).text = value
items = ET.SubElement(project, "ItemGroup")
for identifier, versions in sorted(packages.items()):
    ET.SubElement(items, "PackageDownload", Include=identifier,
                  Version=";".join(f"[{v}]" for v in sorted(versions)))
args.project_directory.mkdir(parents=True, exist_ok=False)
project_file = args.project_directory.resolve() / "Inputs.csproj"
ET.indent(project)
ET.ElementTree(project).write(project_file, encoding="utf-8", xml_declaration=True)
args.log_file.parent.mkdir(parents=True, exist_ok=True)
subprocess.run([str(args.dotnet.resolve(strict=True)), "restore", str(project_file),
                "--configfile", str(configuration), "--verbosity", "quiet",
                f"/flp:verbosity=normal;LogFile={args.log_file.resolve()}"],
               cwd=args.project_directory, check=True)
print(f"Seeded {sum(map(len, packages.values()))} fixed package versions")
