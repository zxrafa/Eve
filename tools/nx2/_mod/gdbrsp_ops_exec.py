import re
import struct
import time


def handle_exec_op(op, parts, rsp, regs):
    if op == "break":
        print("break", parts[1], "->", rsp.cmd(f"Z0,{int(parts[1], 16):x},4"))
    elif op == "breaklr":
        # Break at the current return address (x30 from the last regs/x0).
        lr = regs.get("x30", 0) & 0xFFFFFFFFFFFF
        print("breaklr", hex(lr), "->", rsp.cmd(f"Z0,{lr:x},4"))
    elif op == "unbreakpc":
        pc = regs.get("pc", 0)
        print("unbreakpc", hex(pc), "->", rsp.cmd(f"z0,{pc:x},4"))
    elif op == "unbreak":
        print("unbreak", parts[1], "->", rsp.cmd(f"z0,{int(parts[1], 16):x},4"))
    elif op == "step":
        print("step:", rsp.cmd("s"))
    elif op == "trace":
        # Single-step N instructions, printing pc and x0 (stop early at an optional pc).
        n = int(parts[1])
        stop_at = int(parts[2], 16) if len(parts) > 2 else None
        lo = int(parts[3], 16) if len(parts) > 4 else 0
        hi = int(parts[4], 16) if len(parts) > 4 else 1 << 64
        for _ in range(n):
            rsp.cmd("s")
            r = rsp.regs()
            if lo <= r["pc"] < hi:
                print(f"  t pc={r['pc']:#x} x0={r['x0']:#x} x8={r['x8']:#x}")
            if stop_at is not None and r["pc"] == stop_at:
                break
    elif op == "breakwhen":
        # breakwhen <addr> <reg> <value> [max]: stop at addr only when reg == value.
        addr, reg, want = int(parts[1], 16), parts[2], int(parts[3], 16)
        for _ in range(int(parts[4]) if len(parts) > 4 else 50):
            rsp.cmd(f"Z0,{addr:x},4")
            rsp.cmd("c")
            regs = rsp.regs()
            if regs.get("pc") != addr:
                print("  breakwhen: stopped elsewhere at", hex(regs.get("pc", 0)))
                break
            if regs.get(reg) == want:
                print(f"  breakwhen: hit with {reg}={want:#x}")
                break
            rsp.cmd(f"z0,{addr:x},4")
            rsp.cmd("s")
        print("  " + " ".join(f"{k}={v:#x}" for k, v in regs.items() if k in ("pc", "x0", "x1", "x2", "x19", "x20", "x21", "x22", "x24", "x30")))
    elif op == "flow":
        # flow N stop_hex: single-step N instructions, print only non-sequential pcs (branches)
        n, stop_at = int(parts[1]), int(parts[2], 16)
        prev = rsp.regs().get("pc", 0)
        for _ in range(n):
            rsp.cmd("s")
            r = rsp.regs()
            pc = r.get("pc", 0)
            if pc != prev + 4:
                print(f"  f {prev:#x} -> {pc:#x} x0={r.get('x0', 0):#x}")
            prev = pc
            if pc == stop_at:
                break
    elif op == "hits":
        # hits <max> <addr>...: break at the addresses and, on each hit, print the registers,
        # the frame-pointer chain and the 0x40 bytes at x0, then step past and continue.
        # Stops after <max> hits or when the target stops anywhere else.
        limit, addrs = int(parts[1]), [int(a, 16) for a in parts[2:]]
        for a in addrs:
            rsp.cmd(f"Z0,{a:x},4")
        for hit in range(limit):
            reason = rsp.cmd("c")
            # Several threads can stop at once: read and step the one this reply names.
            tid = re.search(r"thread:([0-9a-f]+);", reason)
            if tid:
                rsp.cmd(f"Hg{tid.group(1)}")
            r = rsp.regs()
            pc = r.get("pc", 0)
            stamp = time.strftime("%H:%M:%S")
            label = (f"hit {hit}" if pc in addrs else f"stopped elsewhere ({reason})") +                     (f" thread {tid.group(1)}" if tid else "")
            print(f"[{stamp}] {label} pc={pc:#x} " + " ".join(
                f"{k}={r.get(k, 0):#x}" for k in ("x0", "x1", "x2", "x19", "x20", "x21", "x30", "sp")), flush=True)
            obj = rsp.mem(r.get("x0", 0), 0x40)
            if len(obj) == 0x40:
                print("   *x0: " + " ".join(f"{w:016x}" for w in struct.unpack("<8Q", obj)), flush=True)
            fp = r.get("x29", 0)
            chain = []
            for _ in range(16):
                d = rsp.mem(fp, 16)
                if len(d) < 16:
                    break
                nfp, ret = struct.unpack("<QQ", d)
                chain.append(f"{ret & 0xFFFFFFFFFFFF:x}")
                if nfp <= fp:
                    break
                fp = nfp
            print("   bt " + " ".join(chain), flush=True)
            if pc not in addrs:
                break
            rsp.cmd(f"z0,{pc:x},4")
            rsp.cmd("s")
            rsp.cmd(f"Z0,{pc:x},4")
        for a in addrs:
            rsp.cmd(f"z0,{a:x},4")
    else:
        return False, regs
    return True, regs
