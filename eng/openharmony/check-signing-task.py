#!/usr/bin/env python3
"""Exercise the built MSBuild task: spaces, incremental outputs, failure preservation."""
from pathlib import Path
import argparse
import os
import shutil
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET

def create_elf(value, kind=3, file_size=1):
    data = bytearray(121)
    data[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<HHI", data, 16, kind, 183, 1)
    struct.pack_into("<Q", data, 32, 64)
    struct.pack_into("<HHH", data, 52, 64, 56, 1)
    struct.pack_into("<IIQ", data, 64, 1, 5, 120)
    struct.pack_into("<QQQ", data, 96, file_size, 1, 1)
    data[120] = value
    return bytes(data)


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
root = Path(tempfile.mkdtemp(prefix="dotnet signing check "))
try:
    output = root / "output files"
    output.mkdir()
    elf = output / "test app"
    elf.write_bytes(create_elf(1))
    elf.chmod(0o700)
    object_file = output / "linker input.o"
    debug_file = output / "detached symbols"
    object_file.write_bytes(create_elf(7, kind=1))
    debug_file.write_bytes(create_elf(8, file_size=0))
    managed = output / "managed.dll"
    managed.write_bytes(b"MZ managed")
    external = root / "external"
    external.mkdir()
    external_elf = external / "library.so"
    external_elf.write_bytes(create_elf(4))
    (output / "linked directory").symlink_to(external, target_is_directory=True)
    signer = root / "signing tool"
    signer.write_text('#!/bin/sh\nset -eu\ncat "$3" > "$5"\nprintf signed >> "$5"\n')
    signer.chmod(0o700)
    project = ET.Element("Project")
    props = ET.SubElement(project, "PropertyGroup")
    for name, value in {
        "MicrosoftNETBuildTasksAssembly": str(task_assembly),
        "OpenHarmonyCodesignEnabled": "true",
        "OpenHarmonySigningTool": str(signer),
        "TargetDir": str(output),
        "IntermediateOutputPath": str(root / "obj") + "/",
    }.items():
        ET.SubElement(props, name).text = value
    ET.SubElement(project, "Import", Project=str(sdk_source / "src/Tasks/Microsoft.NET.Build.Tasks/targets/Microsoft.NET.Sdk.OpenHarmony.targets"))
    ET.SubElement(project, "Target", Name="Build")
    project_path = root / "signing.proj"
    ET.ElementTree(project).write(project_path, encoding="utf-8")
    command = [str(build_dotnet), "msbuild", str(project_path), "-t:Build", "-nologo", "-v:minimal"]
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_CLI_HOME="/tmp/oheco-dotnet-cli-home")
    def run(success):
        result = subprocess.run(command, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        print(result.stdout, end="")
        assert (result.returncode == 0) == success, result.returncode
    run(True)
    signed = elf.read_bytes()
    assert signed == create_elf(1) + b"signed"
    assert elf.stat().st_mode & 0o777 == 0o700
    assert managed.read_bytes() == b"MZ managed"
    assert external_elf.read_bytes() == create_elf(4)
    run(True)
    assert elf.read_bytes() == signed
    elf.write_bytes(create_elf(2))
    run(True)
    assert elf.read_bytes() == create_elf(2) + b"signed"
    elf.write_bytes(create_elf(3))
    signer.write_text("#!/bin/sh\nprintf '{failed}' >&2\nexit 23\n")
    run(False)
    assert elf.read_bytes() == create_elf(3)
    assert len(list(output.iterdir())) == 5
    assert object_file.read_bytes() == create_elf(7, kind=1)
    assert debug_file.read_bytes() == create_elf(8, file_size=0)
    # Also evaluate the default condition on a Linux host without opt-in.
    props.find("OpenHarmonyCodesignEnabled").text = ""
    ET.ElementTree(project).write(project_path, encoding="utf-8")
    run(True)
    # NativeAOT replaces the published executable in an AfterTargets=Publish
    # target; signing before that target would silently leave it unsigned.
    publish = root / "publish files"
    publish.mkdir()
    symbols = publish / "app.dbg"
    symbols.write_bytes(create_elf(9))
    unsigned_native = root / "native binary"
    unsigned_native.write_bytes(create_elf(5))
    signer.write_text('#!/bin/sh\nset -eu\ncat "$3" > "$5"\nprintf signed >> "$5"\n')
    props.find("OpenHarmonyCodesignEnabled").text = "true"
    ET.SubElement(props, "PublishAot").text = "true"
    ET.SubElement(props, "TargetName").text = "app"
    ET.SubElement(props, "NativeSymbolExt").text = ".dbg"
    ET.SubElement(props, "PublishDir").text = str(publish)
    ET.SubElement(project, "Target", Name="Publish")
    copy = ET.SubElement(project, "Target", Name="CopyNativeBinary", AfterTargets="Publish")
    ET.SubElement(copy, "Copy", SourceFiles=str(unsigned_native), DestinationFiles=str(publish / "app"))
    ET.ElementTree(project).write(project_path, encoding="utf-8")
    command[3] = "-t:Publish"
    run(True)
    assert (publish / "app").read_bytes() == create_elf(5) + b"signed"
    assert symbols.read_bytes() == create_elf(9)
    print("ALL SIGNING TASK CHECKS PASSED")
finally:
    shutil.rmtree(root)
