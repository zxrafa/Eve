from .cfg import TYPE_REPLACEMENTS, TYPE_SIZES

def emit_size_check():
    lines = []

    for type, size in TYPE_SIZES.items():
        if type != "void":
            lines.append(f"static_assert(sizeof({type}) == {size});")

    return f"\n{lines}"


# Replaces a type with an arch-specific one, if it exists.
def substitute_type(name, bitness):
    if name in TYPE_REPLACEMENTS:
        return TYPE_REPLACEMENTS[name][bitness]
    else:
        return name


class Argument:
    def __init__(self, type_name, var_name, is_output, is_outptr, is_address):
        self.type_name = type_name
        self.var_name = var_name
        self.is_output = is_output
        self.is_outptr = is_outptr
        self.is_address = is_address


# Parses C-style string declarations for SVCs.
def parse_declaration(declaration, bitness):
    return_type, rest = declaration.split(" ", 1)
    func_name, rest = rest.split("(", 1)
    arg_names, rest = rest.split(")", 1)
    argument_types = []

    return_type = substitute_type(return_type, bitness)
    assert return_type in TYPE_SIZES, f"Unknown type '{return_type}'"

    if arg_names:
        for arg_name in arg_names.split(", "):
            type_name, var_name = arg_name.replace("*", "").split(" ", 1)

            # All outputs must contain out_ in the name.
            is_output = var_name == "out" or var_name.find("out_") != -1

            # User-pointer outputs are not written to registers.
            is_outptr = is_output and arg_name.find("*") == -1

            # Special handling is performed for output addresses to avoid awkwardness
            # in conversion for the 32-bit equivalents.
            is_address = is_output and not is_outptr and \
                type_name in ["Address", "Size"]
            type_name = substitute_type(type_name, bitness)

            assert type_name in TYPE_SIZES, f"Unknown type '{type_name}'"

            argument_types.append(
                Argument(type_name, var_name, is_output, is_outptr, is_address))

    return (return_type, func_name, argument_types)


class RegisterAllocator:
    def __init__(self, num_regs, byte_size, parameter_count):
        self.registers = {}
        self.num_regs = num_regs
        self.byte_size = byte_size
        self.parameter_count = parameter_count

    # Mark the given register as allocated, for use in layout
    # calculation if the NGRN exceeds the ABI parameter count.
    def allocate(self, i):
        assert i not in self.registers, f"Register R{i} already allocated"
        self.registers[i] = True
        return i

    # Calculate the next available location for a register;
    # the NGRN has exceeded the ABI parameter count.
    def allocate_first_free(self):
        for i in range(0, self.num_regs):
            if i in self.registers:
                continue

            self.allocate(i)
            return i

        assert False, "No registers available"

    # Add a single register at the given NGRN.
    # If the index exceeds the ABI parameter count, try to find a
    # location to add it. Returns the output location and increment.
    def add_single(self, ngrn):
        if ngrn >= self.parameter_count:
            return (self.allocate_first_free(), 0)
        else:
            return (self.allocate(ngrn), 1)

    # Add registers at the given NGRN for a data type of
    # the given size. Returns the output locations and increment.
    def add(self, ngrn, data_size, align=True):
        if data_size <= self.byte_size:
            r, i = self.add_single(ngrn)
            return ([r], i)

        regs = []
        inc = ngrn % 2 if align else 0
        remaining_size = data_size
        while remaining_size > 0:
            r, i = self.add_single(ngrn + inc)
            regs.append(r)
            inc += i
            remaining_size -= self.byte_size

        return (regs, inc)


def reg_alloc(bitness):
    if bitness == 0:
        # aapcs32: 4 4-byte registers
        return RegisterAllocator(8, 4, 4)
    elif bitness == 1:
        # aapcs64: 8 8-byte registers
        return RegisterAllocator(8, 8, 8)
