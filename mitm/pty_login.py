#!/usr/bin/env python3
"""cc-routes pty drive: run an interactive CLI flow under a pty with a hard
deadline, capture device-flow output, then SIGKILL. Never hangs: select()
loop with an absolute deadline, kill -9 on exit (oc-routes lesson: a login
flow that ignores SIGTERM survived 7+ minutes under bare `timeout`).

Why: `cmd login` needs ink raw mode, which dies without a tty. Under a pty
it can print its auth URL / device code, which the capture hook records.
We send nothing; the flow is observed, never completed.

Sandbox note: this environment has no pty devices (openpty -> OSError),
so here it exits 3 with a clear message. On an open machine it runs.

Usage:
  python3 pty_login.py [--work DIR] [--deadline S] [--expect SUB]... \
      [--kill-after S] -- [cmd...]
  default cmd: login (via bun --preload hook.mjs)

Env passthrough: LD_PRELOAD / CC_NETLOG / CC_MITM_LOG / NODE_OPTIONS ride
along so both taps keep working under the pty.

Stdlib only (pty, select, signal). Transcript tail to stdout only; the
caller redirects. Device-flow codes are scrubbed from the tail.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive import ensure_npm, setup_cli, latest_version  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "hook.mjs")


def scrub(b: bytes) -> bytes:
    try:
        s = b.decode("utf-8", "replace")
    except Exception:
        return b"[...undecodable...]"
    s = re.sub(r"\b[A-Z0-9]{4,5}-[A-Z0-9]{4,5}\b", "***", s)
    s = re.sub(r"device[_-]?code[\"']?\s*[:=]\s*[\"']?[0-9a-f]{8,}",
               "device_code=***", s, flags=re.I)
    return s.encode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default=os.path.join(HERE, "work"))
    ap.add_argument("--captures", default=os.path.join(HERE, "captures"))
    ap.add_argument("--cli-version", default=None)
    ap.add_argument("--deadline", type=float, default=45)
    ap.add_argument("--expect", action="append", default=[],
                    help="substring to wait for (any match ends run early)")
    ap.add_argument("--kill-after", type=float, default=3.0,
                    help="extra seconds to keep polling after expects seen")
    ap.add_argument("cmd", nargs=argparse.REMAINDER,
                    help="use -- to separate: pty_login.py -- <cmd...>")
    args = ap.parse_args()

    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.captures, exist_ok=True)
    version = args.cli_version or latest_version()
    npm = ensure_npm(args.work)
    cli = setup_cli(args.work, version, npm)

    home = os.path.join(args.work, "home-pty-login")
    shutil.rmtree(home, ignore_errors=True)
    os.makedirs(home)
    log = os.path.join(args.captures, "pty-login.jsonl")
    for suf in ("", ".stdout.txt"):
        try:
            os.unlink(log + suf)
        except FileNotFoundError:
            pass

    env = dict(os.environ)
    env.update(HOME=home, NO_COLOR="1", TERM="xterm-256color",
               CC_MITM_LOG=log, NODE_OPTIONS="--import " + HOOK)
    env.pop("CI", None)
    shimdir = os.path.join(args.work, "bin")
    env["PATH"] = shimdir + os.pathsep + env.get("PATH", "")

    cmd = [c for c in args.cmd if c != "--"]
    if not cmd:
        cmd = ["bun", "--preload", HOOK, cli, "login"]

    import pty
    try:
        pid, fd = pty.fork()
    except OSError as e:
        print(f"pty unavailable in this sandbox ({e}); "
              "auth flows stay headless-crash evidence only",
              file=sys.stderr)
        return 3
    if pid == 0:
        try:
            os.execvpe(cmd[0], cmd, env)
        except Exception as e:
            print(f"exec failed: {e}", file=sys.stderr)
            os._exit(127)

    import select
    out = b""
    t0 = time.time()
    deadline = t0 + args.deadline
    seen = set()
    kill_at = None
    while True:
        now = time.time()
        if kill_at is not None and now >= kill_at:
            break
        if now >= deadline:
            break
        try:
            r, _, _ = select.select([fd], [], [], 0.5)
        except OSError:
            break
        if r:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
            if args.expect:
                for pat in args.expect:
                    if pat.encode() in out[-262144:]:
                        seen.add(pat)
                if len(seen) == len(args.expect) and kill_at is None:
                    kill_at = time.time() + args.kill_after
        try:
            wpid, _ = os.waitpid(pid, os.WNOHANG)
            if wpid == pid and kill_at is None and not args.expect:
                break
        except ChildProcessError:
            break
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        os.waitpid(pid, 0)
    except (ChildProcessError, OSError):
        pass
    try:
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            out += chunk
    except OSError:
        pass
    os.close(fd)
    tail = scrub(out[-8000:])
    sys.stdout.buffer.write(tail + b"\n")
    print(f"[pty] {len(out)}B transcript, expects seen: {sorted(seen)}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
