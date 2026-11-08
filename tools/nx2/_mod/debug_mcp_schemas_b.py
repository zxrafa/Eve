BUTTONS = BUTTONS = ["A", "B", "X", "Y", "L", "R", "ZL", "ZR", "Plus", "Minus", "Up", "Down", "Left", "Right",
           "StickL", "StickR"]
STICK = STICK = {"type": "array", "items": {"type": "number", "minimum": -1, "maximum": 1},
         "minItems": 2, "maxItems": 2, "description": "[x, y], up is +y"}

TOOLS_TAIL = [
    {
        "name": "timeline",
        "description": "Records what the emulator's threads (guest present, GPU front and back, "
                       "Vulkan worker) do and wait for, for the given seconds, and writes a "
                       "Chrome trace (open in ui.perfetto.dev) to the dump directory.",
        "inputSchema": {
            "type": "object",
            "properties": {"seconds": {"type": "number", "minimum": 0.1, "maximum": 30},
                           "detail": {"type": "boolean",
                                      "description": "Also per-draw stages and method calls (slows the GPU threads)"}},
        },
    },
    {
        "name": "switch",
        "description": "Reads or sets a live experiment switch (EDEN_NX2_DMA_WAIT_WRITERS).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "value": {"type": "integer"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "read_memory",
        "description": "Reads up to 64 KiB of the game's guest virtual memory, read only and "
                       "while it runs. 'as' formats it: hex (default), u32, u64 (hex strings) or "
                       "f32. An unmapped page fails with the first unmapped address. Addresses "
                       "are hex strings ('0x8012345000') or numbers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "address": {"type": ["string", "integer"]},
                "size": {"type": "integer", "minimum": 1, "maximum": 65536},
                "as": {"type": "string", "enum": ["hex", "u32", "u64", "f32"]},
            },
            "required": ["address", "size"],
        },
    },
    {
        "name": "search_memory",
        "description": "Finds a byte pattern (hex pairs in memory order: little endian, so 1.0f "
                       "is '0000803f') in the mapped guest memory of the heap region (default) or "
                       "the whole address space, optionally narrowed by start and end. Returns up "
                       "to max_hits (at most 256) addresses; it stops after budget_ms and then "
                       "returns 'next', the start for the following call.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "start": {"type": ["string", "integer"]},
                "end": {"type": ["string", "integer"]},
                "max_hits": {"type": "integer", "minimum": 1, "maximum": 256},
                "regions": {"type": "string", "enum": ["heap", "all"]},
                "budget_ms": {"type": "integer", "minimum": 1, "maximum": 10000},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "read_gpu_memory",
        "description": "Reads up to 64 KiB of GPU virtual memory (e.g. query report and semaphore "
                       "buffers the game reads back) at the next frame end, as the GPU sees it, "
                       "without flushing GPU caches. Tries the bound channel's address space "
                       "first; 'as' as for read_memory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "gpu_address": {"type": ["string", "integer"]},
                "size": {"type": "integer", "minimum": 1, "maximum": 65536},
                "as": {"type": "string", "enum": ["hex", "u32", "u64", "f32"]},
                "timeout_s": {"type": "integer", "minimum": 1, "maximum": 60},
            },
            "required": ["gpu_address", "size"],
        },
    },
    {
        "name": "input",
        "description": "Holds buttons and sticks on player 1 (or the handheld controller) for "
                       "'frames' presented frames from the next present on, then releases; returns "
                       "when done. Buttons are added to the owner's; a given stick replaces the "
                       "owner's. Fails and releases when frames stop (paused or loading) for "
                       "timeout_s (default frames / 20 + 10).",
        "inputSchema": {
            "type": "object",
            "properties": {**{
                "buttons": {"type": "array", "items": {"type": "string", "enum": BUTTONS}},
                "left_stick": STICK,
                "right_stick": STICK,
                "frames": {"type": "integer", "minimum": 1, "maximum": 36000},
            },
                           "timeout_s": {"type": "integer", "minimum": 1, "maximum": 900}},
            "required": ["frames"],
        },
    },
    {
        "name": "input_sequence",
        "description": "Runs input steps back to back, each for exactly its 'frames' presented "
                       "frames, so a camera pan or walk replays identically for an A/B test. A "
                       "step without buttons or sticks leaves the owner's input alone. At most "
                       "1000 steps and 36000 frames.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "steps": {"type": "array", "minItems": 1, "maxItems": 1000,
                          "items": {"type": "object", "properties": {
                "buttons": {"type": "array", "items": {"type": "string", "enum": BUTTONS}},
                "left_stick": STICK,
                "right_stick": STICK,
                "frames": {"type": "integer", "minimum": 1, "maximum": 36000},
            },
                                    "required": ["frames"]}},
                "timeout_s": {"type": "integer", "minimum": 1, "maximum": 900},
            },
            "required": ["steps"],
        },
    },
]
