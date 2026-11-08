import struct
import time


def handle_watch_op(op, parts, rsp, regs):
    if op == "hits":
        # hits <addr> <n> [memreg]: stop at addr n times, printing x0/x1/lr (and 16 bytes at
        # memreg) each time; steps off the breakpoint before resuming.
        addr, n = int(parts[1], 16), int(parts[2])
        memreg = parts[3] if len(parts) > 3 else None
        for i in range(n):
            rsp.cmd(f"Z0,{addr:x},4")
            rsp.cmd("c")
            r = rsp.regs()
            regs = r
            extra = ""
            if memreg and memreg in r:
                extra = " mem=" + rsp.mem(r[memreg], 16).hex()
            print(f"  hit {i} pc={r.get('pc', 0):#x} x0={r.get('x0', 0):#x} x1={r.get('x1', 0):#x} "
                  f"x19={r.get('x19', 0):#x} x20={r.get('x20', 0):#x}" + extra)
            if r.get("pc") != addr:
                break
            rsp.cmd(f"z0,{addr:x},4")
            rsp.cmd("s")
    elif op == "watch":
        # watch <addr> <n> [stopval]: write watchpoint on a u64; print pc, lr and the new value
        # for up to n hits, stopping early once it equals stopval.
        addr, n = int(parts[1], 16), int(parts[2])
        stopval = int(parts[3], 16) if len(parts) > 3 else None
        print("watch ->", rsp.cmd(f"Z2,{addr:x},8"))
        for i in range(n):
            reply = rsp.cmd("c")
            r = rsp.regs()
            regs = r
            d = rsp.mem(addr, 8)
            val = struct.unpack("<Q", d)[0] if len(d) == 8 else None
            chain = []
            fp = r.get("x29", 0)
            for _ in range(6):
                fd = rsp.mem(fp, 16)
                if len(fd) < 16:
                    break
                nfp, ret = struct.unpack("<QQ", fd)
                chain.append(ret & 0xFFFFFFFFFFFF)
                if nfp <= fp:
                    break
                fp = nfp
            print(f"  w{i} {reply[:40]} pc={r.get('pc', 0):#x} lr={r.get('x30', 0) & 0xFFFFFFFFFFFF:#x} value={val if val is None else hex(val)} chain=" + ",".join(f"{c:#x}" for c in chain))
            if stopval is not None and val == stopval:
                break
            # Step off the access with the watchpoint removed, then re-arm it.
            rsp.cmd(f"z2,{addr:x},8")
            rsp.cmd("s")
            rsp.cmd(f"Z2,{addr:x},8")
    elif op == "monitor":
        # monitor <command...>: run a gdbstub monitor command (qRcmd) and print its text.
        reply = rsp.cmd("qRcmd," + " ".join(parts[1:]).encode().hex())
        try:
            print(bytes.fromhex(reply).decode(errors="replace"))
        except ValueError:
            print("monitor:", reply)
    elif op == "raw":
        # raw <packet>: send one packet and print the reply (e.g. qXfer:threads:read::0,ffff).
        print("raw:", rsp.cmd(parts[1]))
    elif op == "sleep":
        import time
        time.sleep(float(parts[1]))
    elif op == "quit":
        return True, regs, True
    return True, regs, False
