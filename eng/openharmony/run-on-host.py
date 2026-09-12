#!/usr/bin/env python3
"""Run a cross-built configure probe on the real host through a PTY zshc session.

Only the copied temporary ELF is signed. The caller's original stays unchanged.
Each run retains the script, output, status and transport log for auditing.
"""
import os
from pathlib import Path
import pty
import select
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

work = Path(__file__).resolve().parent
probe_root = Path(os.environ.get("OHOS_HOST_PROBE_LOG_ROOT", str(work / "host-probes"))).resolve()
probe_root.mkdir(parents=True, exist_ok=True)
run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=probe_root))
original = Path(sys.argv[1]).resolve()
shutil.copyfile(original, run_dir / "probe.unsigned")
shared_root = Path(os.environ.get("OHOS_LINUX_SHARED_ROOT", "/mnt/linux_share")).resolve()
relative = run_dir.relative_to(shared_root)
host_shared_root = os.environ.get("OHOS_HOST_SHARED_ROOT", "/storage/Users/currentUser/dev")
remote = host_shared_root.rstrip("/") + "/" + relative.as_posix()
q = shlex.quote
args = " ".join(q(a) for a in sys.argv[2:])
script = f"""#!/bin/sh
cd {q(remote)} || exit 125
ulimit -c 0
signer=$(command -v binary-sign-tool) || exit 125
if ! "$signer" sign -inFile probe.unsigned -outFile probe -selfSign 1 >sign.log 2>&1; then
  echo 125 > status
  exit 125
fi
chmod +x probe
./probe {args} > stdout 2> stderr
probe_rc=$?
printf '%s\\n' "$probe_rc" > status
exit "$probe_rc"
"""
(run_dir / "run.sh").write_text(script)
master, slave = pty.openpty()
zshc = os.environ.get("OHOS_ZSHC", str(shared_root / "ohos/zshd/zshc"))
client = subprocess.Popen([sys.executable, zshc], stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
os.close(slave)
transcript = bytearray()
sent = False
deadline = time.monotonic() + 90
try:
    while time.monotonic() < deadline:
        readable, _, _ = select.select([master], [], [], 0.25)
        if readable:
            try:
                data = os.read(master, 65536)
            except OSError:
                break
            if not data:
                break
            transcript.extend(data)
            if not sent and b"\x1b[?2004h" in transcript:
                os.write(master, ("sh " + q(remote + "/run.sh") + "; exit $?\n").encode())
                sent = True
        if client.poll() is not None:
            break
    if client.poll() is None:
        client.terminate()
        try:
            client.wait(timeout=5)
        except subprocess.TimeoutExpired:
            client.kill()
            client.wait()
finally:
    os.close(master)
    (run_dir / "transport.log").write_bytes(transcript)
for filename, stream in (("stdout", sys.stdout.buffer), ("stderr", sys.stderr.buffer)):
    path = run_dir / filename
    if path.exists():
        stream.write(path.read_bytes())
status = run_dir / "status"
if not status.exists():
    print("Host probe did not complete; see " + str(run_dir), file=sys.stderr)
    sys.exit(125)
sys.exit(int(status.read_text().strip()))
