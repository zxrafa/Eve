#!/usr/bin/env python3
"""Replay native shader captures and v46-v50 pipeline caches without a GPU."""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)

from _mod.sweep_consts import (
    CacheError, GAMES, GRAPHICS_KEY_SIZE, MAP_MAGIC, STAGES, digest,
)
from _mod.sweep_cache import (
    failure, invoke, parse_cache, summarize, unpack_native_code,
)
from _mod.sweep_runner import make_compiler_fn, prepare_jobs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--compiler", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--spirv-val", default="spirv-val")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--dump-game", default="Mario Tennis Fever")
    parser.add_argument("--native-stage", action="append", default=[], metavar="KEY=STAGE",
                        help="stage established by a capture log for a native filename hash")
    parser.add_argument("--contexts-from", type=Path,
                        help="prior results.json preserving native/cache matches across lowering changes")
    args = parser.parse_args()
    if args.jobs < 1 or args.timeout < 1:
        parser.error("--jobs and --timeout must be positive")
    if not args.compiler.is_file():
        parser.error("--compiler must name the built shader-sweep executable")
    for path in args.inputs:
        if not path.exists():
            parser.error(f"input does not exist: {path}")
    native_stages = {}
    for mapping in args.native_stage:
        key, separator, stage = mapping.partition("=")
        if not separator or not re.fullmatch(r"[0-9a-f]{16}", key) or stage not in STAGES[:6]:
            parser.error("--native-stage requires a 16-digit lowercase hash and a graphics/compute stage")
        native_stages[key] = stage
    compiler = str(args.compiler.resolve())
    validator = shutil.which(args.spirv_val)
    if not validator:
        parser.error("spirv-val is required, install SPIRV-Tools or pass --spirv-val")
    args.output.mkdir(parents=True, exist_ok=True)
    records_dir = args.output / "records"
    records_dir.mkdir(exist_ok=True)
    files = sorted({f.resolve() for p in args.inputs for f in
                    (p.rglob("*.bin") if p.is_dir() else [p])})
    rows, jobs, raw_seen = prepare_jobs(args, parser, files, records_dir, compiler)
    compile_one = make_compiler_fn(compiler, validator, records_dir, args.timeout)
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        for i, row in enumerate(executor.map(compile_one, jobs.values()), 1):
            rows.append(row)
            if i % 100 == 0:
                print(f"compiled {i}/{len(jobs)}", file=sys.stderr)
    (args.output / "results.json").write_text(json.dumps(rows, indent=2) + "\n")
    report = summarize(rows)
    (args.output / "summary.md").write_text(report)
    print(report)
    print(f"{len(files)} input files; {len(raw_seen)} unique native captures; {len(jobs)} compile jobs")
    return int(any(row["status"] != "ok" for row in rows))


if __name__ == "__main__":
    sys.exit(main())
