from collections import defaultdict
import json
from pathlib import Path
import struct
import subprocess

from shader_sweep import invoke, parse_cache, unpack_native_code

def digest(data):
    return hashlib.sha256(data).hexdigest()


def artifact_path(directory, relative):
    path = (directory / relative.replace("\\", "/")).resolve()
    if directory.resolve() not in path.parents:
        raise ValueError("program path escapes its extraction directory")
    return path


def output_path(path, protected_roots):
    path = path.resolve()
    if path.exists() or any(root.resolve() == path or root.resolve() in path.parents
                            for root in protected_roots):
        raise ValueError("output must be a new directory outside all read-only inputs")
    return path


def compute_format(code, control):
    if (not code or len(code) % 16 or len(control) < 104 or
            control[:8] != bytes.fromhex("34127698c9000000")):
        return False
    size, = struct.unpack_from("<I", control, 56)
    stage, = struct.unpack_from("<I", control, 84)
    return 0 < size <= len(code) and size % 16 == 0 and stage >> 16 == 5


def collect_cache_and_manifests(args, records, metadata, runner_bytes):
    cached = defaultdict(list)
    cache_errors = []
    if args.cache_directory:
        for path in sorted(args.cache_directory.glob("*/vulkan.fork-v*.bin")):
            try:
                for environment in parse_cache(path.read_bytes()):
                    lowered = unpack_native_code(environment["code"])
                    if lowered is not None:
                        environment["source"] = str(path)
                        cached[(path.parent.name.lower(), environment["stage"], digest(lowered))].append(environment)
            except (ValueError, OSError) as exc:
                cache_errors.append({"source": str(path), "error": str(exc)})
    programs = {}
    archive_errors = []
    for manifest_path in args.manifests:
        data = manifest_path.read_bytes()
        metadata["manifests"].append({"path": str(manifest_path.resolve()), "sha256": digest(data)})
        manifest = json.loads(data)
        archive_errors.extend(manifest["errors"])
        for program in manifest["programs"]:
            identity = (program["title_id"], program["stage"], program["code_sha256"], program["control_sha256"])
            if identity not in programs:
                programs[identity] = {**program, "directory": manifest_path.parent}
            else:
                programs[identity]["origins"].extend(program["origins"])
    if not programs:
        archive_errors.append({"phase": "coverage", "error": "no extracted shader programs to sweep"})
    (args.output / "run.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return cached, cache_errors, programs, archive_errors


