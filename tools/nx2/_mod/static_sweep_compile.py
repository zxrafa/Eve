import struct
import subprocess
from pathlib import Path

from shader_sweep import invoke
from .static_sweep_jobs import artifact_path, compute_format, digest


def make_compile_one(args, records, validator, cached):
    def compile_one(program):
        identity = digest((program["title_id"] + program["stage"] + program["code_sha256"] +
                           program["control_sha256"]).encode())
        base = {"game": program["game"], "title_id": program["title_id"], "stage": program["stage"],
                "source": program["code"], "control": program["control"],
                "origins": program["origins"], "id": identity,
                "code_sha256": program["code_sha256"], "control_sha256": program["control_sha256"]}
        try:
            for field in ("code", "control"):
                path = artifact_path(program["directory"], program[field])
                data = path.read_bytes()
                if digest(data) != program[f"{field}_sha256"]:
                    raise ValueError(f"{field} SHA256 does not match extraction manifest")
                base["source" if field == "code" else field] = str(path)
        except (OSError, ValueError) as exc:
            return {**base, "status": "error", "phase": "input", "lowered": False,
                    "error": {"message": str(exc)}}
        fmt = program["format"]
        compiler_source = base["source"]
        if fmt is None:
            if base["stage"] != "compute":
                return {**base, "status": "error", "phase": "context", "lowered": False,
                        "error": {"message": f"unverified {base['stage']} bytecode envelope and launch metadata"}}
            if not compute_format(Path(base["source"]).read_bytes(), Path(base["control"]).read_bytes()):
                return {**base, "status": "error", "phase": "context", "lowered": False,
                        "error": {"message": "unverified compute bytecode envelope"}}
            code = Path(base["source"]).read_bytes()
            control = Path(base["control"]).read_bytes()
            code_size, = struct.unpack_from("<I", control, 56)
            bounded = records / f"{identity}.instructions"
            bounded.write_bytes(code[:code_size])
            compiler_source = str(bounded)
            base["archive_allocation_bytes"] = len(code)
            base["declared_code_bytes"] = code_size
            fmt = "instructions"
        lowered_path = records / f"{identity}.lowered"
        command = [str(args.compiler.resolve()), compiler_source, "--stage", base["stage"],
                   "--format", fmt, "--capture-extent"]
        lowered = invoke(command + ["--lower-only", str(lowered_path)], args.timeout)
        if lowered["status"] != "ok":
            row = {**base, **lowered, "lowered": False}
            offset = lowered.get("error", {}).get("offset")
            if isinstance(offset, int):
                data = Path(base["source"]).read_bytes()
                offset += 128 if fmt == "native-header" else 0
                if 0 <= offset <= len(data) - 16:
                    words = struct.unpack_from("<4I", data, offset)
                    row["opcode"] = f"0x{words[0] & 0xfff:03x}"
                    row["instruction"] = [f"{word:08x}" for word in words]
            return row
        matches = cached.get((base["title_id"].lower(), base["stage"], digest(lowered_path.read_bytes())), [])
        if fmt == "native-header":
            header = Path(base["source"]).read_bytes()[:80]
            matches = [env for env in matches if env["code"][:80] == header]
        if matches:
            environment = max(matches, key=lambda env: env["version"])
            env_path, key_path = records / f"{identity}.env", records / f"{identity}.key"
            env_path.write_bytes(environment["bytes"])
            key_path.write_bytes(environment["key"])
            command += ["--environment", str(env_path), "--cache-version", str(environment["version"])]
            if base["stage"] != "compute":
                command += ["--pipeline-key", str(key_path)]
            base["context_source"] = "inferred-compatible-cache-environment"
            base["cache_candidates"] = [{key: env[key] for key in ("source", "entry", "index", "offset", "version")}
                                        for env in matches]
            base["selected_cache_context"] = {key: environment[key] for key in
                                              ("source", "entry", "index", "offset", "version")}
            base["cache_version"] = environment["version"]
        elif base["stage"] == "compute":
            return {**base, "status": "partial", "phase": "context", "lowered": True,
                    "error": {"message": "compute launch and resource context not established"}}
        else:
            base["context_source"] = "static-header-with-synthetic-pipeline-defaults"
        output = records / f"{identity}.spv"
        result = invoke(command + ["--output", str(output)], args.timeout)
        if result["status"] == "ok":
            try:
                validated = subprocess.run([validator, "--target-env", "vulkan1.2", str(output)],
                                           capture_output=True, text=True, timeout=args.timeout)
                if validated.returncode:
                    result.update(status="error", phase="validate", error={"message": validated.stderr.strip()})
                elif matches:
                    result.update(status="partial", phase="validated-compatible-cache")
                else:
                    result.update(status="partial", phase="validated-synthetic")
            except subprocess.TimeoutExpired:
                result.update(status="error", phase="timeout", error={"message": "spirv-val timeout"})
        return {**base, **result, "lowered": True, "command": command + ["--output", str(output)]}
    return compile_one
