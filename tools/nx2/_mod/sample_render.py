import collections
import html
import os
import sys

from .sample_parser import find_module, is_exe

def symbolize_samples(sample_file, exe_name, symbolizer):
    """Returns (thread name, stack outermost first) per sample, inline frames expanded."""
    keys = []
    rvas = set()
    for tag, _qpc, frames in sample_file.samples:
        sample_keys = []
        for depth, address in enumerate(frames):
            # Past the innermost frame these are return addresses: attribute the call.
            lookup = address if depth == 0 else address - 1
            base, path = find_module(sample_file.modules, lookup)
            if base is None:
                sample_keys.append(("label", "[jit]"))
            elif is_exe(path, exe_name):
                sample_keys.append(("rva", lookup - base))
                rvas.add(lookup - base)
            else:
                name = os.path.basename(path.replace("\\", "/"))
                sample_keys.append(("label", "%s+%#x" % (name, lookup - base)))
        keys.append((tag, sample_keys))
    names = symbolizer.resolve(rvas) if rvas else {}
    stacks = []
    for tag, sample_keys in keys:
        stack = []
        for kind, value in sample_keys:
            stack.extend([value] if kind == "label" else names[value])
        stack.reverse()
        thread = sample_file.threads.get(tag, "thread %d" % tag)
        stacks.append((thread, stack))
    return stacks


def summarize(stacks):
    """Per thread: total, self counts, inclusive counts and folded paths."""
    threads = collections.OrderedDict()
    for thread, stack in stacks:
        entry = threads.setdefault(thread, {
            "total": 0, "self": collections.Counter(), "inclusive": collections.Counter(),
            "paths": collections.Counter()})
        entry["total"] += 1
        if stack:
            entry["self"][stack[-1]] += 1
        for function in set(stack):
            entry["inclusive"][function] += 1
        entry["paths"][";".join(stack)] += 1
    return threads


def write_folded(threads, path):
    with open(path, "w") as file:
        for thread, entry in threads.items():
            for stack, count in entry["paths"].most_common():
                file.write("%s;%s %d\n" % (thread, stack, count))


def flamegraph_svg(threads, width=1600, row=16):
    """A plain flame graph: one root per thread, width proportional to samples."""
    root = {"name": "all", "count": 0, "children": collections.OrderedDict()}
    for thread, entry in threads.items():
        for stack, count in entry["paths"].items():
            node = root
            node["count"] += count
            for name in [thread] + (stack.split(";") if stack else []):
                node = node["children"].setdefault(
                    name, {"name": name, "count": 0, "children": collections.OrderedDict()})
                node["count"] += count
    rects = []
    depth_max = [0]

    def emit(node, x, depth):
        depth_max[0] = max(depth_max[0], depth)
        w = width * node["count"] / max(root["count"], 1)
        if w >= 0.5:
            hue = 30 + (hash(node["name"]) % 40)
            rects.append((x, depth, w, node["name"], node["count"], hue))
        child_x = x
        for child in node["children"].values():
            emit(child, child_x, depth + 1)
            child_x += width * child["count"] / max(root["count"], 1)

    emit(root, 0.0, 0)
    height = (depth_max[0] + 1) * row
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" font-family="monospace" font-size="11">'
             % (width, height)]
    for x, depth, w, name, count, hue in rects:
        y = height - (depth + 1) * row
        label = html.escape(name)
        percent = 100.0 * count / max(root["count"], 1)
        parts.append('<g><title>%s (%d samples, %.2f%%)</title><rect x="%.1f" y="%d" width="%.1f" height="%d" '
                     'fill="hsl(%d,80%%,60%%)" stroke="white" stroke-width="0.5"/>'
                     % (label, count, percent, x, y, w, row - 1, hue))
        if w > 40:
            text = label[:int(w / 7)]
            parts.append('<text x="%.1f" y="%d">%s</text>' % (x + 2, y + row - 4, text))
        parts.append("</g>")
    parts.append("</svg>")
    return "\n".join(parts)


def report(threads, hz, top=25, paths=30, out=sys.stdout):
    for thread, entry in threads.items():
        total = entry["total"]
        seconds = total / hz if hz else 0
        out.write("== %s: %d samples (%.1f s at %d Hz)\n" % (thread, total, seconds, hz))
        out.write("-- self\n")
        for function, count in entry["self"].most_common(top):
            out.write("%6.2f%% %7d  %s\n" % (100.0 * count / total, count, function))
        out.write("-- inclusive\n")
        for function, count in entry["inclusive"].most_common(top):
            out.write("%6.2f%% %7d  %s\n" % (100.0 * count / total, count, function))
        out.write("-- top call paths (outermost first)\n")
        for stack, count in entry["paths"].most_common(paths):
            out.write("%6.2f%% %7d  %s\n" % (100.0 * count / total, count, stack.replace(";", " > ")))
        out.write("\n")
