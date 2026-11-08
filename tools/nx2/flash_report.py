#!/usr/bin/env python3
"""Builds flash_<frame>.html next to each report of an EDEN_NX2_FLASH_WATCH directory.

Each page lists the outputs of the flash frame in GPU order with their tiles in the two frames
before, the flash frame and the two after. Thumbnails are scaled by the brightest tile of the
frames around the flash, so a tile that flashes saturates; NaN/Inf tiles are magenta and tiles
with hot texels orange. The box is the flashed region.

Usage: python3 -I tools/nx2/flash_report.py <watch dir>
"""
import base64
import html
import json
import struct
import sys
import zlib
from pathlib import Path

import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)

from _mod.flash_render import (
    CENTER, LABELS, WINDOW, describe, fmt_values, png, thumbnails, tile_means,
)

def build(report_path):
    lines = [json.loads(line) for line in report_path.read_text().splitlines() if line.strip()]
    flash, outputs = lines[0], lines[1:]
    blob = (report_path.parent / flash["tile_file"]).read_bytes()
    x0, y0, x1, y1 = flash["region"]
    box = (f"left:{x0 * 100:.2f}%;top:{y0 * 100:.2f}%;"
           f"width:{(x1 - x0) * 100:.2f}%;height:{(y1 - y0) * 100:.2f}%")
    first = flash["first_abnormal"]
    rows = []
    for output in outputs:
        images = thumbnails(output, blob)
        cells = "".join(
            f'<td class="thumb"><div><img src="data:image/png;base64,{image}">'
            f'<span style="{box}"></span></div></td>' if image else "<td>-</td>"
            for image in images)
        shaders = " ".join(output["shaders"][:4]) + (
            f' +{len(output["shaders"]) - 4}' if len(output["shaders"]) > 4 else "")
        region = output["region"]
        classes = ["abnormal"] if output["abnormal"] else []
        if output["index"] == first:
            classes.append("first")
        ratio = output["mean_ratio"]
        peak = output["peak_ratio"]
        rows.append(
            f'<tr id="o{output["index"]}" class="{" ".join(classes)}">'
            f'<td>{output["index"]}</td><td>{html.escape(describe(output))}'
            f'<br><code>{html.escape(shaders)}</code></td>'
            f'<td>{"-" if ratio is None else f"{ratio:.3g}"}</td>'
            f'<td>{"-" if peak is None else f"{peak:.3g}"}</td>'
            f'<td class="v">{fmt_values(region["mean"])}</td>'
            f'<td class="v">{fmt_values(region["peak"])}</td>'
            f'<td class="v">{fmt_values(region["bad"])}</td>'
            f'<td class="v">{fmt_values(region["hot"])}</td>'
            f"{cells}</tr>")
    first_link = f'<a href="#o{first}">output {first}</a>' if first is not None else "none"
    page = f"""<!doctype html><meta charset="utf-8"><title>Flash at frame {flash["frame"]}</title>
<style>
body {{ font: 13px sans-serif; background: #111; color: #ddd; }}
table {{ border-collapse: collapse; }}
td, th {{ border: 1px solid #333; padding: 3px 5px; vertical-align: middle; }}
tr.abnormal {{ background: #3a2a10; }}
tr.first {{ background: #6a2020; }}
code {{ color: #9ab; font-size: 11px; }}
.v {{ white-space: nowrap; }}
.thumb div {{ position: relative; width: 160px; }}
.thumb img {{ width: 160px; image-rendering: pixelated; display: block; }}
.thumb span {{ position: absolute; outline: 1px solid #0f0; }}
</style>
<h1>Flash at frame {flash["frame"]} ({flash["seconds"]:.1f} s)</h1>
<p>Frames {", ".join(map(str, flash["frames"]))}; trigger <code>{html.escape(flash["trigger"])}</code>,
{len(flash["tiles"])} tiles brighter, region ({x0:.2f},{y0:.2f})-({x1:.2f},{y1:.2f}).
First abnormal output: {first_link}; {flash["abnormal"]} of {flash["outputs"]} abnormal.
Values per column are frames {", ".join(LABELS)}, measured in the region.</p>
<table><tr><th>#</th><th>output</th><th>mean ratio</th><th>peak ratio</th><th>mean</th>
<th>peak</th><th>NaN/Inf</th><th>hot</th>{"".join(f"<th>{label}</th>" for label in LABELS)}</tr>
{chr(10).join(rows)}
</table>
"""
    out = report_path.with_suffix(".html")
    out.write_text(page, encoding="utf-8")
    culprit = describe(outputs[first]) if first is not None else "none"
    print(f'{out}: frame {flash["frame"]}, first abnormal: {culprit}')


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    reports = sorted(Path(sys.argv[1]).glob("flash_*.jsonl"))
    if not reports:
        sys.exit(f"no flash_*.jsonl in {sys.argv[1]}")
    for report in reports:
        build(report)


if __name__ == "__main__":
    main()
