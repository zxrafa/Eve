#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2026 Eden Emulator Project
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: Copyright 2023 yuzu Emulator Project
# SPDX-License-Identifier: GPL-2.0-or-later


import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)

from _svc_mod.defs import SVCS
from _svc_mod.cfg import (
    BIT_32, BIT_64, REG_SIZES, SKIP_WRAPPERS, SUFFIX_NAMES,
    TYPE_REPLACEMENTS, TYPE_SIZES,
)
from _svc_mod.parser_alloc import (
    Argument, RegisterAllocator, emit_size_check, parse_declaration,
    reg_alloc, substitute_type,
)
from _svc_mod.emitters import (
    emit_gather, emit_lines, emit_scatter, emit_wrapper, get_registers,
)
from _svc_mod.templates_h import COPYRIGHT, EPILOGUE_H, PROLOGUE_H
from _svc_mod.templates_cpp import EPILOGUE_CPP, PROLOGUE_CPP

def emit_call(bitness, names, suffix):
    bit_size = REG_SIZES[bitness]*8
    indent = "    "
    lines = [
        f"static void Call{bit_size}(Core::System& system, u32 imm, std::span<uint64_t, 8> args) {{",
        f"{indent}switch (SvcId(imm)) {{"
    ]

    for _, name in names:
        lines.append(f"{indent}case SvcId::{name}: return SvcWrap_{name}{suffix}(system, args);")

    lines.append(f"{indent}default: UNREACHABLE_MSG(\"Unhandled SVC {{:#x}}\", imm);")
    lines.append(f"{indent}}}")
    lines.append("}")

    return f"\n{lines}"


def build_fn_declaration(return_type, name, arguments):
    arg_list = ["Core::System& system"]
    for arg in arguments:
        type_name = "uint64_t" if arg.is_address else arg.type_name
        pointer = "*" if arg.is_output and not arg.is_outptr else ""
        arg_list.append(f"{type_name}{pointer} {arg.var_name}")

    return f"{return_type} {name}({', '.join(arg_list)});"


def build_enum_declarations():
    lines = ["enum class SvcId : u32 {"]
    indent = "    "

    for imm, decl in SVCS:
        _, name, _ = parse_declaration(decl, BIT_64)
        lines.append(f"{indent}{name} = {hex(imm)},")

    lines.append("};")
    return f"\n{lines}"


def main():
    arch_fw_declarations = [[], []]
    svc_fw_declarations = []
    wrapper_fns = []
    names = []

    for imm, decl in SVCS:
        return_type, name, arguments = parse_declaration(decl, BIT_64)

        if imm not in SKIP_WRAPPERS:
            svc_fw_declarations.append(
                build_fn_declaration(return_type, name, arguments))

        names.append([imm, name])

    for bitness in range(2):
        byte_size = REG_SIZES[bitness]
        suffix = SUFFIX_NAMES[bitness]

        for imm, decl in SVCS:
            if imm in SKIP_WRAPPERS:
                continue

            parse_result = parse_declaration(decl, bitness)
            return_type, name, arguments = parse_result

            register_info = get_registers(parse_result, bitness)
            wrapper_fns.append(
                emit_wrapper(name, suffix, register_info, arguments, byte_size))
            arch_fw_declarations[bitness].append(
                build_fn_declaration(return_type, name + suffix, arguments))

    call_32 = emit_call(BIT_32, names, SUFFIX_NAMES[BIT_32])
    call_64 = emit_call(BIT_64, names, SUFFIX_NAMES[BIT_64])
    enum_decls = build_enum_declarations()

    with open("src/core/hle/kernel/svc.h", "w") as f:
        f.write(COPYRIGHT)
        f.write(PROLOGUE_H)
        f.write(f"\n{svc_fw_declarations}")
        f.write("\n\n")
        f.write(f"\n{arch_fw_declarations[BIT_32]}")
        f.write("\n\n")
        f.write(f"\n{arch_fw_declarations[BIT_64]}")
        f.write("\n\n")
        f.write(enum_decls)
        f.write(EPILOGUE_H)

    with open("src/core/hle/kernel/svc.cpp", "w") as f:
        f.write(COPYRIGHT)
        f.write(PROLOGUE_CPP)
        f.write(emit_size_check())
        f.write("\n\n")
        f.write(f"\n\n{wrapper_fns}")
        f.write("\n\n")
        f.write(call_32)
        f.write("\n\n")
        f.write(call_64)
        f.write(EPILOGUE_CPP)

    print(f"Done (emitted {len(names)} definitions)")


if __name__ == "__main__":
    main()
