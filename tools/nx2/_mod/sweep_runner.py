from collections import defaultdict
import json
import re
import struct
import subprocess

from .sweep_consts import GAMES, STAGES, digest
from .sweep_cache import CacheError, failure, invoke, parse_cache, unpack_native_code


def prepare_jobs(args, parser, files, records_dir, compiler):
    rows, jobs, cache_index = [], {}, defaultdict(list)
    prior_contexts = defaultdict(list)
    if args.contexts_from:
        for row in json.loads(args.contexts_from.read_text()):
            if row.get("kind") == "native" and "env" in row:
                prior_contexts[row["native_id"]].append(row)
    for path in files:
        if not re.fullmatch(r"vulkan(?:\.fork-v\d+)?\.bin", path.name):
            continue
        game = GAMES.get(path.parent.name.lower(), path.parent.name)
        try:
            envs = list(parse_cache(path.read_bytes()))
            for env in envs:
                identity = digest(game.encode() + env["bytes"] + env["key"] + bytes([env["version"]]))
                if identity not in jobs:
                    env_path = records_dir / f"{identity}.env"
                    key_path = records_dir / f"{identity}.key"
                    env_path.write_bytes(env["bytes"])
                    key_path.write_bytes(env["key"])
                    jobs[identity] = {"id": identity, "game": game, "stage": env["stage"],
                                      "source": str(path), "offset": env["offset"],
                                      "kind": "cache", "env": str(env_path),
                                      "key": str(key_path), "version": env["version"]}
                lowered = unpack_native_code(env["code"])
                if lowered is not None:
                    match = cache_index[digest(lowered)]
                    if identity not in match:
                        match.append(identity)
        except (CacheError, OSError) as exc:
            rows.append({"game": game, "source": str(path), **failure("input", str(exc))})
    header_stages = {}
    for path in files:
        rejected = re.fullmatch(r"rejected-stage-([1-5])-[0-9a-f]+\.bin", path.name)
        if rejected:
            header_stages[digest(path.read_bytes()[128:])] = STAGES[int(rejected[1]) - 1]
    raw_seen = set()
    for path in files:
        match = re.fullmatch(r"(?:[0-9a-f]+-(gfx|cs)-[0-9a-f]+|rejected-stage-(\d+)-[0-9a-f]+)\.bin", path.name)
        if not match:
            continue
        source = path.read_bytes()
        identity = digest(source)
        if identity in raw_seen:
            continue
        raw_seen.add(identity)
        rejected_stage = int(match[2]) if match[2] is not None else None
        stage = STAGES[rejected_stage - 1] if rejected_stage is not None and 1 <= rejected_stage <= 5 else None
        if match[1] == "cs":
            stage = "compute"
        if stage is None:
            stage = header_stages.get(identity)
        explicit_stage = native_stages.get(path.name.split("-")[0])
        if explicit_stage:
            if stage is not None and explicit_stage != stage:
                parser.error(f"explicit stage conflicts with capture metadata: {path}")
            stage = explicit_stage
        fmt = "native-header" if rejected_stage is not None else "instructions"
        lower_path = records_dir / f"{identity}.lowered"
        cmd = [compiler, str(path), "--format", fmt, "--lower-only", str(lower_path)]
        if stage:
            cmd += ["--stage", stage]
        result = invoke(cmd, args.timeout)
        if (stage is None and result["status"] != "ok" and
                "outside geometry stage" in result.get("error", {}).get("message", "")):
            stage = "geometry"
            result = invoke(cmd + ["--stage", stage], args.timeout)
        base = {"game": args.dump_game, "id": identity, "source": str(path),
                "native_id": identity, "stage": stage or "unknown", "kind": "native"}
        if result["status"] != "ok":
            offset = result.get("error", {}).get("offset")
            if result.get("phase") == "lower" and isinstance(offset, int):
                offset += 128 if fmt == "native-header" else 0
                if 0 <= offset <= len(source) - 16:
                    words = struct.unpack_from("<4I", source, offset)
                    base["opcode"] = f"0x{words[0] & 0xfff:03x}"
                    base["instruction"] = [f"{word:08x}" for word in words]
            rows.append({**base, **result})
            continue
        matches = [jobs[target] for target in cache_index.get(digest(lower_path.read_bytes()), [])
                   if jobs[target]["game"] == args.dump_game]
        if not matches:
            matches = prior_contexts.get(identity, [])
        if matches:
            compatible = False
            for cached in matches:
                if stage is not None and cached["stage"] != stage:
                    continue
                compatible = True
                new_id = digest((identity + cached["env"] + cached["key"]).encode())
                jobs[new_id] = {**cached, **base, "id": new_id, "stage": cached["stage"], "format": fmt}
            if not compatible:
                rows.append({**base, **failure("context", "cached stage disagrees with captured stage")})
        elif stage is not None:
            jobs[identity] = {**base, "format": fmt}
        else:
            rows.append({**base, **failure("context", "instruction-only dump has no matching cached stage/header")})

    return rows, jobs, raw_seen


def make_compiler_fn(compiler, validator, records_dir, timeout):
    def compile_one(job):
        output = records_dir / f"{job['id']}.spv"
        command = [compiler, "--output", str(output)]
        if job["kind"] == "native":
            command += [job["source"], "--stage", job["stage"], "--format", job["format"]]
        if "env" in job:
            command += ["--environment", job["env"], "--cache-version", str(job["version"])]
            if job["stage"] != "compute":
                command += ["--pipeline-key", job["key"]]
        result = invoke(command, args.timeout)
        if result["status"] == "ok":
            try:
                validation = subprocess.run([validator, "--target-env", "vulkan1.2", str(output)],
                                            capture_output=True, text=True, timeout=args.timeout)
                if validation.returncode:
                    result.update(failure("validate", validation.stderr.strip() or validation.stdout.strip()))
                else:
                    result["phase"] = "validated"
            except subprocess.TimeoutExpired:
                result.update(failure("timeout", "spirv-val timeout"))
        return {**job, **result, "command": command}
    return compile_one
