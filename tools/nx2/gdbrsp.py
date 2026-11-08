#!/usr/bin/env python3
# Minimal GDB remote-serial-protocol client for Eden's gdbstub (AArch64 guests).
# Usage: gdbrsp.py <port> <script>
# Script lines:  break <hexaddr> | unbreak <hexaddr> | continue | regs | x0 | mem <hexaddr|xN> <len> | bt <hexaddr|sp> <count>
#                | quit
import socket
import struct
import sys

import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)

from _mod.gdbrsp_client import REGS, Rsp
from _mod.gdbrsp_ops_exec import handle_exec_op
from _mod.gdbrsp_ops_mem import handle_mem_op
from _mod.gdbrsp_ops_watch import handle_watch_op


def main():
    import re
    import time
    rsp = Rsp(int(sys.argv[1]))
    # Until the guest process exists the stub answers with a bogus thread id; commands sent then
    # are lost, so wait for a real one.
    for _ in range(120):
        reason = rsp.cmd("?")
        m = re.search(r"thread:([0-9a-f]+);", reason)
        if m and int(m.group(1), 16) < 0x10000:
            break
        time.sleep(0.5)
    print("halt reason:", reason)
    regs = {}
    for line in open(sys.argv[2]):
        parts = line.split()
        if not parts or parts[0].startswith("#"):
            continue
        op = parts[0]
        handled, regs = handle_exec_op(op, parts, rsp, regs)
        if handled:
            continue
        handled, regs, should_quit = handle_mem_op(op, parts, rsp, regs)
        if should_quit:
            break
        if handled:
            continue
        _, regs, should_quit = handle_watch_op(op, parts, rsp, regs)
        if should_quit:
            break
    rsp.s.close()


if __name__ == "__main__":
    main()
