#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lower every extracted shader and separate captured replay from synthetic context."""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys


import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)

from shader_sweep import invoke, parse_cache, unpack_native_code, summarize

from _mod.static_sweep_compile import make_compile_one
from _mod.static_sweep_jobs import (
    artifact_path, collect_cache_and_manifests, compute_format, digest,
    output_path,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", nargs="+", type=Path)
    parser.add_argument("--compiler", required=True, type=Path)
    parser.add_argument("--cache-directory", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--read-only-root", action="append", required=True, type=Path)
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--spirv-val", default="spirv-val")
    args = parser.parse_args()
    if args.jobs < 1 or args.timeout < 1 or not args.compiler.is_file():
        parser.error("positive jobs/timeout and a compiler executable are required")
    try:
        args.output = output_path(args.output, args.read_only_root +
                                  [path.parent for path in args.manifests] +
                                  ([args.cache_directory] if args.cache_directory else []))
    except ValueError as exc:
        parser.error(str(exc))
    validator = shutil.which(args.spirv_val)
    if not validator:
        parser.error("spirv-val is required")
    args.output.mkdir(parents=True)
    records = args.output / "records"
    records.mkdir(exist_ok=True)
    metadata = {"compiler": str(args.compiler.resolve()),
                "compiler_sha256": digest(args.compiler.read_bytes()),
                "runner_sha256": digest(Path(__file__).read_bytes()),
                "validator": validator, "validator_sha256": digest(Path(validator).read_bytes()),
                "manifests": [], "read_only_roots": [str(path.resolve()) for path in args.read_only_root],
                "cache_directory": str(args.cache_directory) if args.cache_directory else None,
                "cache_context_policy": "one compatible candidate per allocation; association remains inferred"}
    cached, cache_errors, programs, archive_errors = collect_cache_and_manifests(
        args, records, metadata, Path(__file__).read_bytes()
    )
    compile_one = make_compile_one(args, records, validator, cached)
    results = []
    with (args.output / "results.jsonl").open("w", encoding="utf-8") as journal:
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            for index, result in enumerate(executor.map(compile_one, programs.values()), 1):
                results.append(result)
                journal.write(json.dumps(result) + "\n")
                journal.flush()
                if index % 250 == 0:
                    print(f"Processed {index}/{len(programs)}", file=sys.stderr, flush=True)
    (args.output / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    (args.output / "archive-errors.json").write_text(json.dumps(archive_errors + cache_errors, indent=2) + "\n", encoding="utf-8")
    (args.output / "summary.md").write_text(summarize(results), encoding="utf-8")
    print(json.dumps({"programs": len(results), "lowered": sum(row["lowered"] for row in results),
                      "phases": dict(Counter(row["phase"] for row in results)),
                      "archive_errors": len(archive_errors), "cache_errors": len(cache_errors)}))
    return int(any(row["status"] != "ok" for row in results) or bool(archive_errors or cache_errors))


if __name__ == "__main__":
    sys.exit(main())
