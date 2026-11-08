#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Extract verified NVN2 shader allocations without running games or accessing keys."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys


import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)

from _mod.extract_core import digest, extract, walk_container

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--source", action="append", default=[], metavar="TITLE_ID=PATH")
    parser.add_argument("--read-only-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    library = args.read_only_root.resolve()
    output = args.output.resolve()
    if output == library or library in output.parents:
        parser.error("output must be outside the read-only library")
    if output.exists():
        parser.error("output must be a new scratch directory")
    sources = []
    coverage_errors = []
    if args.inventory:
        for game in json.loads(args.inventory.read_text(encoding="utf-8")):
            coverage_errors.extend({"game": game["name"], "phase": "inventory", **error}
                                   for error in game["errors"])
            ids = {p["title_id"] for p in game["programs"]}
            if len(ids) != 1:
                coverage_errors.append({"game": game["name"], "path": game["directory"],
                                        "phase": "coverage", "title_ids": sorted(ids),
                                        "error": "no unique loose-program title ID; select package sources separately"})
                continue
            title_id = next(iter(ids))
            candidates = [candidate for candidate in game["candidates"]
                          if Path(candidate["path"]).suffix.lower() not in
                          (".tex", ".json", ".presetb", ".meminfo")]
            if not candidates:
                coverage_errors.append({"game": game["name"], "path": game["directory"],
                                        "phase": "coverage", "title_id": title_id,
                                        "error": "no supported loose shader candidates; asset container needs another reader"})
            for candidate in candidates:
                sources.append({"game": game["name"], "title_id": title_id, "path": candidate["path"]})
    for specification in args.source:
        title_id, separator, path = specification.partition("=")
        if not separator or not re.fullmatch("[0-9a-fA-F]{16}", title_id):
            parser.error("--source requires TITLE_ID=PATH")
        sources.append({"game": title_id.upper(), "title_id": title_id.upper(), "path": path})
    if not sources and not coverage_errors:
        parser.error("no shader archive sources selected")
    for source in sources:
        path = Path(source["path"]).resolve()
        if path != library and library not in path.parents:
            parser.error(f"source is outside the declared read-only root: {path}")
        if not re.fullmatch("[0-9a-fA-F]{16}", source["title_id"]):
            parser.error("invalid inventory title id")
    output.mkdir(parents=True, exist_ok=True)
    result = extract(sources, output)
    result["errors"].extend(coverage_errors)
    (output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"archives": len(result["archives"]), "programs": len(result["programs"]),
                      "stages": dict(Counter(p["stage"] for p in result["programs"])),
                      "errors": len(result["errors"])}))
    return int(bool(result["errors"]))


if __name__ == "__main__":
    sys.exit(main())
