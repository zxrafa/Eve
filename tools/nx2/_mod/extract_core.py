import hashlib
from pathlib import Path
import sys

from shader_archive import ArchiveError, find_bnsh, parse_bnsh, parse_sarc
from shader_containers import (
    MAX_ALLOCATION, dcx_decompress, parse_bnd4, parse_cgsb, parse_shn, zstd_decompress,
)

def digest(data):
    return hashlib.sha256(data).hexdigest()


def walk_container(data, name, depth=0):
    if depth > 12:
        raise ArchiveError("excessive container nesting")
    magic = data[:4]
    if magic == bytes.fromhex("28b52ffd"):
        yield from walk_container(zstd_decompress(data), name + "!zstd", depth + 1)
    elif magic == b"DCX\0":
        yield from walk_container(dcx_decompress(data), name + "!dcx", depth + 1)
    elif magic in (b"SARC", b"BND4"):
        members = parse_sarc(data) if magic == b"SARC" else parse_bnd4(data)
        for member, payload in members:
            try:
                yield from walk_container(payload, name + "!" + member, depth + 1)
            except (ArchiveError, ValueError) as exc:
                yield {"member": name + "!" + member, "error": str(exc)}
    elif magic == b"FSHA":
        for offset, bnsh in find_bnsh(data):
            yield from walk_container(bnsh, name + f"!BNSH@{offset:x}", depth + 1)
    elif magic in (b"BNSH", b"CGSB", b"SHN!"):
        parser = {b"BNSH": parse_bnsh, b"CGSB": parse_cgsb, b"SHN!": parse_shn}[magic]
        for record in parser(data):
            yield {"member": name, **record}
    elif name.lower().endswith((".json", ".presetb", ".meminfo", ".tex", ".byml", ".yaml")):
        return
    else:
        raise ArchiveError(f"unsupported container magic {magic.hex()}")


def extract(sources, output):
    programs = {}
    archives = []
    errors = []
    for source in sources:
        path = Path(source["path"])
        game = source["game"]
        title_id = source["title_id"]
        print(f"Reading {game}: {path.name}", file=sys.stderr, flush=True)
        try:
            before = path.stat()
            if before.st_size > MAX_ALLOCATION:
                raise ArchiveError("archive exceeds in-memory limit; needs selective reader")
            data = path.read_bytes()
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ArchiveError("source changed during read")
            archive = {**source, "size": len(data), "sha256": digest(data), "records": 0}
            for record in walk_container(data, path.name):
                if "error" in record:
                    errors.append({**source, **record})
                    continue
                code = record.pop("code")
                control = record.pop("control")
                code_hash, control_hash = digest(code), digest(control)
                identity = (title_id, record["stage"], code_hash, control_hash)
                if identity not in programs:
                    directory = output / "programs" / title_id
                    directory.mkdir(parents=True, exist_ok=True)
                    controls = output / "controls"
                    controls.mkdir(exist_ok=True)
                    code_path = directory / f"{code_hash}-{record['stage']}.bin"
                    control_path = controls / f"{control_hash}.bin"
                    code_path.write_bytes(code)
                    control_path.write_bytes(control)
                    programs[identity] = {
                        "game": game, "title_id": title_id, "stage": record["stage"],
                        "code": code_path.relative_to(output).as_posix(),
                        "control": control_path.relative_to(output).as_posix(),
                        "code_sha256": code_hash, "control_sha256": control_hash,
                        "format": "native-header" if record["stage"] in
                                  ("vertex", "tess-control", "tess-eval", "geometry", "fragment") else None,
                        "context": "archive header only; runtime resources unavailable",
                        "origins": [],
                    }
                programs[identity]["origins"].append({"source": str(path), **record})
                archive["records"] += 1
            archives.append(archive)
        except (OSError, ArchiveError, ValueError) as exc:
            errors.append({**source, "error": str(exc)})
    return {"schema_version": 1, "archives": archives, "programs": list(programs.values()), "errors": errors}
