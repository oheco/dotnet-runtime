#!/usr/bin/env python3
"""Archive a final signed installation with explicit portable permissions.

The shared filesystem's Linux mode bits differ from its host mode bits. Classify
ELF programs and interpreter scripts from their contents instead of trusting
those bits. File payloads, including signatures and debug symbols, stay intact.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct
import tarfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("root", type=Path)
parser.add_argument("archive", type=Path)
parser.add_argument("--prefix", required=True)
parser.add_argument("--epoch", type=int, required=True, help="Timestamp of the verified source commit")
args = parser.parse_args()
root = args.root.resolve(strict=True)
if not root.is_dir() or not args.prefix or "/" in args.prefix or args.prefix in {".", ".."}:
    parser.error("Need a directory and one safe archive prefix component")
if args.archive.resolve().is_relative_to(root):
    parser.error("The output archive must be outside the installation tree")


def executable(path):
    with path.open("rb") as stream:
        header = stream.read(64)
        if header.startswith(b"#!"):
            return True
        if len(header) < 64 or header[:6] != b"\x7fELF\x02\x01":
            return False
        kind = struct.unpack_from("<H", header, 16)[0]
        offset = struct.unpack_from("<Q", header, 32)[0]
        size, count = struct.unpack_from("<HH", header, 54)
        if kind not in (2, 3) or size < 56 or offset + size * count > path.stat().st_size:
            return False
        for index in range(count):
            stream.seek(offset + size * index)
            segment = stream.read(56)
            kind, flags = struct.unpack_from("<II", segment)
            file_size = struct.unpack_from("<Q", segment, 32)[0]
            if file_size and (kind == 2 or (kind == 1 and flags & 1)):
                return True
    return False


inventory = []
args.archive.parent.mkdir(parents=True, exist_ok=True)
with args.archive.open("xb") as destination:
    with gzip.GzipFile(filename="", mode="wb", fileobj=destination, mtime=args.epoch, compresslevel=6) as compressed:
        # The native host tar truncates PAX linkpath records to 100 bytes.
        # Its GNU long-link support preserves complete SDK pack symlink targets.
        with tarfile.open(fileobj=compressed, mode="w|", format=tarfile.GNU_FORMAT) as archive:
            for path in [root, *sorted(root.rglob("*"))]:
                relative = path.relative_to(root).as_posix()
                name = args.prefix if relative == "." else args.prefix + "/" + relative
                info = archive.gettarinfo(str(path), arcname=name)
                info.uid = info.gid = 0
                info.uname = info.gname = "root"
                info.mtime = args.epoch
                info.pax_headers = {}
                # Emit complete files even when a build used hardlinks between
                # its pack and framework directories.
                if info.islnk():
                    info.type = tarfile.REGTYPE
                    info.linkname = ""
                    info.size = path.stat().st_size
                if info.issym():
                    if not (path.parent / info.linkname).resolve().is_relative_to(root):
                        raise ValueError("Symlink escapes installation: " + relative)
                    info.mode = 0o777
                    archive.addfile(info)
                elif info.isdir():
                    info.mode = 0o755
                    archive.addfile(info)
                elif info.isfile():
                    info.mode = 0o755 if executable(path) else 0o644
                    with path.open("rb") as stream:
                        digest = hashlib.file_digest(stream, "sha256").hexdigest()
                        stream.seek(0)
                        archive.addfile(info, stream)
                    inventory.append(dict(path=relative, size=info.size, mode=oct(info.mode), sha256=digest))
                else:
                    raise ValueError("Unsupported installation file type: " + relative)

with args.archive.open("rb") as stream:
    digest = hashlib.file_digest(stream, "sha256").hexdigest()
Path(str(args.archive) + ".sha256").write_text(f"{digest}  {args.archive.name}\n")
Path(str(args.archive) + ".files.json").write_text(json.dumps(inventory, indent=2) + "\n")
print(f"Archived {len(inventory)} files: {args.archive.name} ({args.archive.stat().st_size} bytes, SHA-256 {digest})")
