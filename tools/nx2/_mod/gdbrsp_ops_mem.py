import struct
import time


def handle_mem_op(op, parts, rsp, regs):
    if op == "continue":
        print("stop:", rsp.cmd("c"))
    elif op == "continue_async":
        # Resume without waiting for a stop reply (pair with interrupt).
        pkt = b"c"
        rsp.s.sendall(b"$" + pkt + b"#" + f"{sum(pkt) & 0xff:02x}".encode())
    elif op == "x0":
        r = rsp.regs()
        regs = r
        print(f"  pc={r.get('pc', 0):#x} x0={r.get('x0', 0):#x} x1={r.get('x1', 0):#x} lr={r.get('x30', 0):#x}")
    elif op == "regs":
        regs = rsp.regs()
        print(" ".join(f"{k}={v:#x}" for k, v in regs.items()))
    elif op == "mem":
        base, _, off = parts[1].partition("+")
        a = (regs[base] if base in regs else int(base, 16)) + (int(off, 16) if off else 0)
        data = rsp.mem(a, int(parts[2], 0))
        for i in range(0, len(data), 16):
            words = [struct.unpack_from("<Q", data, i + j)[0] for j in range(0, min(16, len(data) - i) - 7, 8)]
            print(f"  {a + i:#x}: " + " ".join(f"{w:016x}" for w in words))
    elif op == "fp":
        # Walk the frame-pointer chain: print return addresses.
        fp = regs.get("x29", 0)
        for _ in range(int(parts[1]) if len(parts) > 1 else 12):
            d = rsp.mem(fp, 16)
            if len(d) < 16:
                break
            nfp, ret = struct.unpack("<QQ", d)
            print(f"  frame fp={fp:#x} ret={ret & 0xFFFFFFFFFFFF:#x}")
            if nfp <= fp:
                break
            fp = nfp
    elif op == "interrupt":
        # Stop a running target (Ctrl-C) and print the stop reply.
        rsp.s.sendall(b"")
        print("interrupt:", rsp._read_packet())
    elif op == "threads":
        # threads [frames]: every thread's pc, lr and frame-pointer chain.
        ids = []
        r = rsp.cmd("qfThreadInfo")
        while r.startswith("m"):
            ids += [t for t in r[1:].split(",") if t]
            r = rsp.cmd("qsThreadInfo")
        depth = int(parts[1]) if len(parts) > 1 else 16
        for t in ids:
            rsp.cmd(f"Hg{t}")
            r = rsp.regs()
            chain = []
            fp = r.get("x29", 0)
            for _ in range(depth):
                d = rsp.mem(fp, 16)
                if len(d) < 16:
                    break
                nfp, ret = struct.unpack("<QQ", d)
                chain.append(ret & 0xFFFFFFFFFFFF)
                if nfp <= fp:
                    break
                fp = nfp
            print(f"thread {t} pc={r.get('pc', 0):#x} lr={r.get('x30', 0) & 0xFFFFFFFFFFFF:#x} "
                  f"x0={r.get('x0', 0):#x} x1={r.get('x1', 0):#x} chain=" + ",".join(f"{c:#x}" for c in chain))
    elif op == "selthread":
        # selthread <lo> <hi>: select the first thread whose pc, lr or frame chain falls in
        # [lo, hi); later regs/mem ops then read that thread.
        lo, hi = int(parts[1], 16), int(parts[2], 16)
        ids = []
        r = rsp.cmd("qfThreadInfo")
        while r.startswith("m"):
            ids += [t for t in r[1:].split(",") if t]
            r = rsp.cmd("qsThreadInfo")
        for t in ids:
            rsp.cmd(f"Hg{t}")
            r = rsp.regs()
            cands = [r.get("pc", 0), r.get("x30", 0) & 0xFFFFFFFFFFFF]
            fp = r.get("x29", 0)
            for _ in range(8):
                d = rsp.mem(fp, 16)
                if len(d) < 16:
                    break
                nfp, ret = struct.unpack("<QQ", d)
                cands.append(ret & 0xFFFFFFFFFFFF)
                if nfp <= fp:
                    break
                fp = nfp
            if any(lo <= c < hi for c in cands):
                regs = r
                print("selthread", t)
                break
        else:
            print("selthread: none")
    else:
        return False, regs, False
    return True, regs, False
