#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026 Eden Emulator Project
# SPDX-License-Identifier: GPL-3.0-or-later

"""Compare the historical full-table and bounded-window mapping implementations.

Run from any directory with Python 3 and a C++20 compiler:
    python3 tools/nx2/test_mapping_table_equivalence.py --cxx clang++
    CXX=clang++ python3 tools/nx2/test_mapping_table_equivalence.py --sanitize

Both revisions must exist locally. Production sources are never modified. Scratch
headers only rename the namespace and expose private members for state/lookup checks.
This audits the historical optimization, not the current Nx2GpuMemoryRegistry.
"""

import argparse
import os
from pathlib import Path
import shlex
import subprocess
import tempfile


OLD_REVISION = "badc91ebce6b6cb44eabe67f7aa0dbbc6abd9e46"
NEW_REVISION = "c4137dc79500428483e5c680f6a4a668bbb3532b"
HEADER = "src/core/hle/service/nvdrv/devices/nx2_gpu_mapping_table.h"


import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)

from _mod.mapping_cxx_a import CXX_PART_1
from _mod.mapping_cxx_b import CXX_PART_2
from _mod.mapping_cxx_c import CXX_PART_3

CXX_SOURCE = CXX_PART_1 + CXX_PART_2 + CXX_PART_3

def extract(repo: Path, revision: str, namespace: str) -> str:
    source = subprocess.check_output(
        ["git", "show", f"{revision}:{HEADER}"], cwd=repo, text=True
    )
    if source.count("namespace Service::Nvidia::Devices {") != 1:
        raise ValueError(f"Unexpected namespace in {revision}")
    if source.count("\nprivate:\n") != 1:
        raise ValueError(f"Unexpected access sections in {revision}")
    return source.replace("Service::Nvidia::Devices", namespace).replace(
        "\nprivate:\n", "\npublic:\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default=os.environ.get("CXX", "clang++"))
    parser.add_argument("--seed", type=lambda value: int(value, 0), default=0x4D415050494E47)
    parser.add_argument("--operations", type=int, default=2_000_000)
    parser.add_argument("--sanitize", action="store_true", help="Enable address/undefined sanitizers")
    parser.add_argument("--work-dir", type=Path, help="Parent directory for temporary compiler files")
    args = parser.parse_args()
    if args.operations < 0 or not 0 <= args.seed < 2**64:
        parser.error("operations must be nonnegative and seed must fit u64")
    repo = Path(__file__).resolve().parents[2]
    if args.work_dir:
        args.work_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mapping-equivalence-", dir=args.work_dir) as directory:
        work = Path(directory)
        for name, revision, namespace in (
            ("reference.h", OLD_REVISION, "MappingReference"),
            ("optimized.h", NEW_REVISION, "MappingOptimized"),
        ):
            (work / name).write_text(extract(repo, revision, namespace))
        source = work / "equivalence.cpp"
        source.write_text(CXX_SOURCE)
        binary = work / "equivalence"
        command = shlex.split(args.cxx) + [
            "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
            "-I", str(repo / "src"), str(source), "-o", str(binary),
        ]
        if args.sanitize:
            command += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
        print(f"Reference: {OLD_REVISION}\nOptimized: {NEW_REVISION}", flush=True)
        print(shlex.join(command), flush=True)
        subprocess.run(command, check=True)
        subprocess.run([str(binary), str(args.seed), str(args.operations)], check=True)


if __name__ == "__main__":
    main()
