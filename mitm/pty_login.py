#!/usr/bin/env python3
"""Run `cmd login` under a pty so ink gets raw mode, capturing any auth-flow
network (device-code init, polling) via the capture hook.

One-shot experiment helper, not part of the default matrix: the login flow
is interactive by design. We send nothing; the flow either prints a URL and
polls (captured) or waits (killed by timeout).

Usage: python3 pty_login.py [--work DIR] [--timeout S]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive import ensure_npm, setup_cli, latest_version  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "hook.mjs")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default=os.path.join(HERE, "work"))
    ap.add_argument("--captures", default=os.path.join(HERE, "captures"))
    ap.add_argument("--cli-version", default=None)
    ap.add_argument("--timeout", type=int, default=45)
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
    # working npm shim (see drive.py)
    shimdir = os.path.join(args.work, "bin")
    env["PATH"] = shimdir + os.pathsep + env.get("PATH", "")

    import pty
    m_primary, m_sub = pty.openpty()
    p = subprocess.Popen(
        ["bun", "--preload", HOOK, cli, "login"], stdin=m_sub,
        stdout=m_sub, stderr=subprocess.STDOUT, env=env,
        cwd=os.path.join(args.captures, "bin-empty"), close_fds=True)
    os.close(m_sub)
    out = b""
    t0 = time.time()
    try:
        import select
        while time.time() - t0 < args.timeout:
            if p.poll() is not None:
                break
            r, _, _ = select.select([m_primary], [], [], 1.0)
            if r:
                try:
                    chunk = os.read(m_primary, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                out += chunk
        # give polling a grace window, then kill
        time.sleep(5)
        while time.time() - t0 < args.timeout + 10:
            if p.poll() is not None:
                break
            r, _, _ = select.select([m_primary], [], [], 1.0)
            if r:
                try:
                    chunk = os.read(m_primary, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                out += chunk
    finally:
        if p.poll() is None:
            p.kill()
        try:
            while True:
                chunk = os.read(m_primary, 65536)
                if not chunk:
                    break
                out += chunk
        except OSError:
            pass
        os.close(m_primary)
    with open(log + ".stdout.txt", "wb") as f:
        f.write(out)
    print(f"rc={p.returncode} output={len(out)}B log={log}")
    try:
        n = sum(1 for _ in open(log))
        print(f"events={n}")
    except FileNotFoundError:
        print("events=0 (no log)")


if __name__ == "__main__":
    sys.exit(main())
