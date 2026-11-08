TOOLS_HEAD = [
    {
        "name": "status",
        "description": "Game title, program id, build, renderer, paused state, presented frame "
                       "count and fps (measured over fps_window_ms), dump directory, live log "
                       "filter and the shader hashes rejected at runtime.",
        "inputSchema": {
            "type": "object",
            "properties": {"fps_window_ms": {"type": "integer", "minimum": 0, "maximum": 5000}},
        },
    },
    {
        "name": "screenshot",
        "description": "PNG of the next presented frame (16:9, default 720 lines). Fails when no "
                       "frame is presented within timeout_s (paused or loading).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "height": {"type": "integer", "minimum": 144, "maximum": 2160},
                "save": {"type": "boolean", "description": "Also write it into the dump directory."},
                "timeout_s": {"type": "integer", "minimum": 1, "maximum": 30},
            },
        },
    },
    {
        "name": "log_tail",
        "description": "Log lines kept in memory since the game booted. Without 'after', the newest "
                       "'limit' lines; with 'after' (the 'next' of an earlier call), the lines "
                       "logged since, oldest first. 'contains' keeps lines with that substring.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "after": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 5000},
                "contains": {"type": "string"},
            },
        },
    },
    {
        "name": "log_filter",
        "description": "Replaces the live log filter, e.g. '*:Info HW.GPU:Debug Shader:Debug'. "
                       "Returns the previous one. Lines filtered out are never logged.",
        "inputSchema": {
            "type": "object",
            "properties": {"filter": {"type": "string"}},
            "required": ["filter"],
        },
    },
    {
        "name": "capture_frame",
        "description": "EDEN_NX2_FRAME_DUMP for the next frame, now: every pass colour target, "
                       "dispatch storage image and the present source as PNG and .raw.zst, plus "
                       "manifest.jsonl. 'sampled' also reads back every sampled texture with its "
                       "sampler state; 'buffers' records every draw's and dispatch's uniform and "
                       "storage buffers (kind: buffer, buffer_<hash>.bin.zst) and dispatch group "
                       "counts (kind: launch). Returns "
                       "the directory, summary, entry counts and the first manifest entries. "
                       "'index' builds index.html with frame_dump_index.py.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sampled": {"type": "boolean"},
                "buffers": {"type": "boolean"},
                "timeout_s": {"type": "integer", "minimum": 1, "maximum": 600},
                "manifest_lines": {"type": "integer", "minimum": 0, "maximum": 5000},
                "index": {"type": "boolean"},
            },
        },
    },
    {
        "name": "capture_image",
        "description": "One PNG of a capture made in this session, by entry name (the manifest "
                       "'name', without extension), e.g. '0042_pass007_d120-180_rt0'.",
        "inputSchema": {
            "type": "object",
            "properties": {"directory": {"type": "string"}, "name": {"type": "string"}},
            "required": ["directory", "name"],
        },
    },
    {
        "name": "reject_shaders",
        "description": "EDEN_NX2_REJECT_HASH at runtime: rejects (or with reject=false restores) "
                       "native programs by native program key (shader dump names) or shader hash "
                       "(frame dump 'shaders'); their cached pipelines are dropped at the next "
                       "frame end. With no hashes, lists the rejected ones.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hashes": {"type": "array", "items": {"type": "string"}},
                "reject": {"type": "boolean"},
                "timeout_s": {"type": "integer", "minimum": 0, "maximum": 60},
            },
        },
    },
    {
        "name": "sample",
        "description": "Sampling profiler: pauses the named host threads about 1000 times a second "
                       "for the given seconds and returns where they were (self, self <- caller, "
                       "inclusive counts per function). Also writes the report and its folded "
                       "stacks to the dump directory. Windows only.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "threads": {"type": "string",
                            "description": "Comma separated thread names; default GPU,GPUBack"},
                "seconds": {"type": "number", "minimum": 1, "maximum": 60},
                "max_chars": {"type": "integer", "minimum": 0},
            },
        },
    },
]
