#!/usr/bin/env python3
"""Check that each SDK copy hook runs before the corresponding MSBuild copy."""
from pathlib import Path
import argparse
import os
import shutil
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("sdk_source", type=Path)
parser.add_argument("sdk_build", type=Path)
parser.add_argument("dotnet", type=Path)
args = parser.parse_args()
sdk_source = args.sdk_source.resolve(strict=True)
sdk_build = args.sdk_build.resolve(strict=True)
build_dotnet = args.dotnet.resolve(strict=True)
task_assembly = sdk_build / "artifacts/bin/Release/Sdks/Microsoft.NET.Sdk/tools/net10.0/Microsoft.NET.Build.Tasks.dll"
if not task_assembly.is_file():
    parser.error("Build the SDK task assembly first")
root = Path(tempfile.mkdtemp(prefix="dotnet native copy check "))
cases = [
    ("_CopyFilesMarkedCopyLocal", "ReferenceCopyLocalPaths", "copylocal", "SkipCopyUnchangedFiles"),
    ("_CopyOutOfDateSourceItemsToOutputDirectory", "_SourceItemsToCopyToOutputDirectory", "newest", ""),
    ("_CopyOutOfDateSourceItemsToOutputDirectoryAlways", "_SourceItemsToCopyToOutputDirectoryAlways", "always", ""),
    ("_CopyDifferingSourceItemsToOutputDirectory", "_SourceItemsToCopyToOutputDirectoryIfDifferent", "different", ""),
    ("_CopyResolvedFilesToPublishPreserveNewest", "_ResolvedFileToPublishPreserveNewest", "newest", ""),
    ("_CopyResolvedFilesToPublishAlways", "_ResolvedFileToPublishAlways", "different", "SkipCopyUnchangedFiles"),
    ("_CopyResolvedFilesToPublishIfDifferent", "_ResolvedFileToPublishIfDifferent", "different", ""),
]
try:
    data = bytearray(121)
    data[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<HHI", data, 16, 3, 183, 1)
    struct.pack_into("<Q", data, 32, 64)
    struct.pack_into("<HHH", data, 52, 64, 56, 1)
    struct.pack_into("<IIQ", data, 64, 1, 5, 120)
    struct.pack_into("<QQQ", data, 96, 1, 1, 1)
    source = root / "app"
    source.write_bytes(data)
    for index, (target_name, item_name, mode, skip_property) in enumerate(cases):
        output = root / str(index)
        output.mkdir()
        destination = output / "app"
        destination.write_bytes(data)
        os.utime(destination, (source.stat().st_mtime - 60,) * 2)
        project = ET.Element("Project")
        props = ET.SubElement(project, "PropertyGroup")
        for name, value in {
            "MicrosoftNETBuildTasksAssembly": str(task_assembly),
            "_OpenHarmonyPrepareNativeCopy": "true",
            "OpenHarmonyCodesignEnabled": "false",
            "ExpectReplacement": "true",
            "OutDir": str(output) + "/",
            "PublishDir": str(output) + "/",
        }.items():
            ET.SubElement(props, name).text = value
        if skip_property:
            ET.SubElement(props, skip_property).text = "true"
        items = ET.SubElement(project, "ItemGroup")
        item = ET.SubElement(items, item_name, Include=str(source))
        ET.SubElement(item, "TargetPath").text = "app"
        ET.SubElement(item, "RelativePath").text = "app"
        ET.SubElement(project, "Import", Project=str(sdk_source / "src/Tasks/Microsoft.NET.Build.Tasks/targets/Microsoft.NET.Sdk.OpenHarmony.targets"))
        attributes = {"Name": target_name}
        if mode == "newest":
            attributes.update(Inputs=str(source), Outputs=str(destination))
        target = ET.SubElement(project, "Target", **attributes)
        ET.SubElement(target, "Error", Condition=f"'$(ExpectReplacement)' == 'true' and Exists('{destination}')",
                      Text="Native destination was not prepared before the copy target.")
        ET.SubElement(target, "Copy", SourceFiles=str(source), DestinationFiles=str(destination),
                      SkipUnchangedFiles="false" if mode == "always" else "true")
        project_path = root / f"copy-{index}.proj"
        ET.ElementTree(project).write(project_path, encoding="utf-8")
        command = [str(build_dotnet), "msbuild", str(project_path),
                   "-t:" + target_name, "-nologo", "-v:minimal"]
        environment = dict(os.environ, DOTNET_CLI_HOME="/tmp/oheco-dotnet-cli-home",
                           HTTP_PROXY="socks5://127.0.0.1:10808", HTTPS_PROXY="socks5://127.0.0.1:10808")
        subprocess.run(command, env=environment, check=True)
        assert destination.read_bytes() == source.read_bytes()
        if mode != "always":
            before = destination.stat().st_ino
            subprocess.run(command + ["/p:ExpectReplacement=false"], env=environment, check=True)
            assert destination.stat().st_ino == before
        print("PASS " + target_name)
    print("ALL NATIVE COPY HOOKS PASSED")
finally:
    shutil.rmtree(root)
