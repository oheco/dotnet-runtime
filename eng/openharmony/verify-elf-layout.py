#!/usr/bin/env python3
"""Audit release ELF architecture, signatures and accidental GNU dependencies.

This checks the presence of signing metadata; native execution remains required
to validate that the host actually accepts the signatures and dependencies.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("root", type=Path)
parser.add_argument("--allow-unsigned", action="store_true")
args = parser.parse_args()
root = args.root.resolve(strict=True)
records = []
native_pe_files = []
errors = []
gnu = {"libc.so.6", "libm.so.6", "libdl.so.2", "libpthread.so.0", "libstdc++.so.6", "libgcc_s.so.1"}

for path in sorted(root.rglob("*")):
    if path.is_symlink() or not path.is_file():
        continue
    with path.open("rb") as file:
        header = file.read(64)
        if header[:4] in (b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe",
                          b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe",
                          b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
                          b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"):
            errors.append(f"{path.relative_to(root)}: Mach-O binary in OHOS distribution")
            continue
        if header.startswith(b"MZ"):
            relative = str(path.relative_to(root))
            if len(header) < 64:
                errors.append(f"{relative}: truncated DOS/PE header")
                continue
            pe_offset = struct.unpack_from("<I", header, 60)[0]
            file.seek(pe_offset)
            coff = file.read(24)
            if len(coff) != 24 or coff[:4] != b"PE\0\0":
                errors.append(f"{relative}: invalid PE header")
                continue
            optional_size = struct.unpack_from("<H", coff, 20)[0]
            optional = file.read(optional_size)
            magic = struct.unpack_from("<H", optional)[0] if len(optional) >= 2 else 0
            directories = {0x10b: 96, 0x20b: 112}.get(magic)
            clr_directory = directories + 14 * 8 if directories is not None else 0
            clr_rva = (struct.unpack_from("<I", optional, clr_directory)[0]
                       if clr_directory and len(optional) >= clr_directory + 8 else 0)
            # Managed .NET assemblies are PE files on every OS, including R2R.
            # Native Windows PE files have no CLR data directory.
            if not clr_rva:
                native_pe_files.append(relative)
                errors.append(f"{relative}: native PE binary in OHOS distribution")
            continue
    if not header.startswith(b"\x7fELF"):
        continue
    relative = str(path.relative_to(root))
    if len(header) < 64 or header[4:6] != b"\x02\x01":
        errors.append(f"{relative}: expected ELF64 little endian")
        continue
    kind, machine = struct.unpack_from("<HH", header, 16)
    loadable = False
    table_offset = struct.unpack_from("<Q", header, 32)[0]
    entry_size, entry_count = struct.unpack_from("<HH", header, 54)
    if kind in (2, 3) and entry_size >= 56 and table_offset + entry_size * entry_count <= path.stat().st_size:
        with path.open("rb") as file:
            for index in range(entry_count):
                file.seek(table_offset + entry_size * index)
                segment = file.read(56)
                segment_type, flags = struct.unpack_from("<II", segment)
                file_size = struct.unpack_from("<Q", segment, 32)[0]
                if file_size and (segment_type == 2 or (segment_type == 1 and flags & 1)):
                    loadable = True
                    break
    if machine != 183:
        errors.append(f"{relative}: wrong machine {machine}")
    report = subprocess.run(["readelf", "-W", "-l", "-d", "-S", "-V", str(path)],
                            check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
    needed = re.findall(r"\(NEEDED\).*?\[(.*?)\]", report)
    rpaths = re.findall(r"\((?:RPATH|RUNPATH)\).*?\[(.*?)\]", report)
    interpreter = re.search(r"Requesting program interpreter: (.*?)\]", report)
    signed = bool(re.search(r"\s\.codesign\s", report))
    if loadable and not signed and not args.allow_unsigned:
        errors.append(f"{relative}: missing .codesign section")
    if gnu.intersection(needed) or re.search(r"Name: (GLIBC_|GLIBCXX_|CXXABI_)", report):
        errors.append(f"{relative}: GNU runtime dependency")
    if interpreter and "ld-linux" in interpreter.group(1):
        errors.append(f"{relative}: GNU ELF interpreter")
    if any("/tmp/" in value or "/home/" in value or "/mnt/" in value for value in rpaths):
        errors.append(f"{relative}: build directory in runtime library path")
    with path.open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    records.append(dict(path=relative, type=kind, machine=machine, signed=signed, loadable=loadable,
                        needed=needed, rpaths=rpaths,
                        interpreter=interpreter.group(1) if interpreter else None,
                        size=path.stat().st_size, sha256=digest))

print(json.dumps(dict(root=str(root), elf_files=records, native_pe_files=native_pe_files, errors=errors), indent=2))
raise SystemExit(bool(errors))
