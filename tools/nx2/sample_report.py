#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026 Eden Emulator Project
# SPDX-License-Identifier: GPL-3.0-or-later

"""Reports an EDEN_NX2_SAMPLE_PROFILE file (src/common/nx2_sample_profile.h).

    python3 -I tools/nx2/sample_report.py nx2_samples_<pid>.bin --exe eve.exe [--folded out.txt] [--svg out.svg]

Symbolizes eve.exe frames with llvm-symbolizer (eve.pdb next to the exe), caching the
result next to the sample file, and prints per thread: self and inclusive time by function and
the top call paths. Other modules show as module+offset, code outside any module as [jit].
"""

import argparse
import collections
import html
import json
import os
import struct
import subprocess
import sys

import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)

from _mod.sample_parser import (
    KIND_END, KIND_MODULE, KIND_SAMPLE, KIND_THREAD,
    SampleFile, Symbolizer, find_module, is_exe, parse,
)
from _mod.sample_render import (
    flamegraph_svg, report, summarize, symbolize_samples, write_folded,
)

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("samples")
    parser.add_argument("--exe", default="eve.exe", help="eve.exe of the build (eve.pdb next to it)")
    parser.add_argument("--symbolizer", default="llvm-symbolizer")
    parser.add_argument("--no-inlines", action="store_true",
                        help="attribute samples to the real (not inlined) functions; MSVC's inline "
                             "records can name the wrong callers")
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--paths", type=int, default=30)
    parser.add_argument("--folded", help="write folded stacks (flamegraph.pl input)")
    parser.add_argument("--svg", help="write a flame graph")
    args = parser.parse_args()

    with open(args.samples, "rb") as file:
        sample_file = parse(file.read())
    if not sample_file.complete:
        print("note: the file ends without its end record (cut short)", file=sys.stderr)
    symbolizer = Symbolizer(args.exe if os.path.exists(args.exe) else None,
                            args.samples + (".symcache-noinl.json" if args.no_inlines
                                            else ".symcache.json"),
                            args.symbolizer, not args.no_inlines)
    stacks = symbolize_samples(sample_file, os.path.basename(args.exe), symbolizer)
    threads = summarize(stacks)
    report(threads, sample_file.hz, args.top, args.paths)
    if args.folded:
        write_folded(threads, args.folded)
    if args.svg:
        with open(args.svg, "w") as file:
            file.write(flamegraph_svg(threads))


if __name__ == "__main__":
    main()
