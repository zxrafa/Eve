from .cfg import TYPE_SIZES
from .parser_alloc import reg_alloc

def get_registers(parse_result, bitness):
    output_alloc = reg_alloc(bitness)
    input_alloc = reg_alloc(bitness)
    return_type, _, arguments = parse_result

    return_write = []
    output_writes = []
    input_reads = []

    input_ngrn = 0
    output_ngrn = 0

    # Run the input calculation.
    for arg in arguments:
        if arg.is_output and not arg.is_outptr:
            input_ngrn += 1
            continue

        regs, increment = input_alloc.add(
            input_ngrn, TYPE_SIZES[arg.type_name], align=True)
        input_reads.append([arg.type_name, arg.var_name, regs])
        input_ngrn += increment

    # Include the return value if this SVC returns a value.
    if return_type != "void":
        regs, increment = output_alloc.add(
            output_ngrn, TYPE_SIZES[return_type], align=False)
        return_write.append([return_type, regs])
        output_ngrn += increment

    # Run the output calculation.
    for arg in arguments:
        if not arg.is_output or arg.is_outptr:
            continue

        regs, increment = output_alloc.add(
            output_ngrn, TYPE_SIZES[arg.type_name], align=False)
        output_writes.append(
            [arg.type_name, arg.var_name, regs, arg.is_address])
        output_ngrn += increment

    return (return_write, output_writes, input_reads)


# Collects possibly multiple source registers into the named C++ value.
def emit_gather(sources, name, type_name, reg_size):
    get_fn = f"GetArg{reg_size*8}"

    if len(sources) == 1:
        s, = sources
        line = f"{type_name} {name} = Convert<{type_name}>({get_fn}(args, {s}));"
        return [line]

    var_type = f"std::array<uint{reg_size*8}_t, {len(sources)}>"
    lines = [
        f"{var_type} {name}_gather{{}};"
    ]
    for i in range(0, len(sources)):
        lines.append(f"{name}_gather[{i}] = {get_fn}(args, {sources[i]});")

    lines.append(f"{type_name} {name} = Convert<{type_name}>({name}_gather);")
    return lines


# Produces one or more statements which assign the named C++ value
# into possibly multiple registers.
def emit_scatter(destinations, name, reg_size):
    set_fn = f"SetArg{reg_size*8}"
    reg_type = f"uint{reg_size*8}_t"

    if len(destinations) == 1:
        d, = destinations
        line = f"{set_fn}(args, {d}, Convert<{reg_type}>({name}));"
        return [line]

    var_type = f"std::array<{reg_type}, {len(destinations)}>"
    lines = [f"auto {name}_scatter = Convert<{var_type}>({name});"]
    for i in range(0, len(destinations)):
        lines.append(f"{set_fn}(args, {destinations[i]}, {name}_scatter[{i}]);")
    return lines


def emit_lines(lines, indent='    '):
    output_lines = []
    first = True
    for line in lines:
        if line and not first:
            output_lines.append(indent + line)
        else:
            output_lines.append(line)
        first = False

    return f"\n{output_lines}"


# Emit a C++ function to wrap a guest SVC.
def emit_wrapper(wrapped_fn, suffix, register_info, arguments, byte_size):
    return_write, output_writes, input_reads = register_info
    lines = [
        f"static void SvcWrap_{wrapped_fn}{suffix}(Core::System& system, std::span<uint64_t, 8> args) {{"
    ]

    for input_type, var_name, sources in input_reads:
        lines += emit_gather(sources, var_name, input_type, byte_size)

    # Build the call.
    call_arguments = ["system"]
    for arg in arguments:
        if arg.is_output and not arg.is_outptr:
            call_arguments.append(f"std::addressof({arg.var_name})")
        else:
            call_arguments.append(arg.var_name)

    # Get everything ready.
    for output_type, var_name, _, is_address in output_writes:
        output_type = "uint64_t" if is_address else output_type
        lines.append(f"{output_type} {var_name}{{}};")

    line = ""
    for return_type, _ in return_write:
        line += f"{return_type} ret = "

    line += f"{wrapped_fn}{suffix}({', '.join(call_arguments)});"
    lines.append(line)

    # Write back the return value and outputs.
    for _, destinations in return_write:
        lines += emit_scatter(destinations, "ret", byte_size)
    for _, var_name, destinations, _ in output_writes:
        lines += emit_scatter(destinations, var_name, byte_size)

    # Finish.
    return emit_lines(lines) + "\n}"
