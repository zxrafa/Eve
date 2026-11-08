import struct

from .cli_fixtures import MAXWELL_EXIT, NATIVE_EXIT, environment


class OotCliCases:
    def test_oot_extended_compare_accumulation(self):
        for control in (0x08f25120, 0x08f05100, 0x08705130, 0x09725110,
                        0x09f05100, 0x09f45120, 0x0a745120):
            with self.subTest(control=hex(control)):
                source = self.write("oot-compare.bin", struct.pack(
                    "<4I", 0xff007c0c, 9, control, 0x000fe400) + NATIVE_EXIT)
                capture = self.write("shader.env", environment(50, 4))
                self.run_cli(source, "--environment", capture, "--cache-version", 50,
                             "--output", self.output)
                self.validate()

    def test_oot_shadowed_register_forms(self):
        instructions = (
            (0x2fe97a20, 0x01401200, 0x00410000, 0x000fe200),
            (0xfff47321, 0x000100ff, 0x00000400, 0x000fe200),
            (0x07f57a23, 0x00c01e00, 0x00010018, 0x040fe200),
            (0x14f37621, 0x01001000, 0x00010000, 0x000fe200),
            (0x5fdf7808, 0x3f800000, 0x02800000, 0x000fe200),
            (0xffda7923, 0, 0x00007800, 0x000e2800),
        )
        uniform_move = struct.pack("<4I", 0x00007c02, 0, 0x08000f00, 0)
        for instruction in instructions:
            with self.subTest(opcode=hex(instruction[0] & 0xfff)):
                source = self.write("oot-shadow.bin", uniform_move +
                                    struct.pack("<4I", *instruction) + NATIVE_EXIT)
                self.run_cli(source, "--lower-only", self.output)

    def test_oot_extended_compare_preserves_aliased_predicates(self):
        for control in (0x08f25120, 0x08f05100, 0x08705130, 0x09725110,
                        0x09f05100, 0x09f45120, 0x0a745120):
            source = self.write("oot-predicates.bin", struct.pack(
                "<4I", 0xff007c0c, 9, control, 0x000fe400) + NATIVE_EXIT)
            self.run_cli(source, "--lower-only", self.output)
            words = struct.unpack("<" + "Q" * (self.output.stat().st_size // 8),
                                  self.output.read_bytes())
            for mask in range(128):
                for value in (0, 1, 0xffffffff):
                    original = [bool(mask & (1 << i)) for i in range(7)] + [True]
                    predicates = original.copy()
                    registers = {225: value, 255: 0}
                    read_predicate = lambda encoded: predicates[encoded & 7] != bool(encoded & 8)
                    for word in words:
                        bits = lambda start, size: (word >> start) & ((1 << size) - 1)
                        if word == MAXWELL_EXIT:
                            break
                        if not read_predicate(bits(16, 4)):
                            continue
                        if word >> 48 == 0x38e8:
                            packed = sum(int(predicates[i]) << i for i in range(7))
                            selected = bits(20, 7)
                            registers[bits(0, 8)] = ((registers[bits(8, 8)] & ~selected) |
                                                      (packed & selected))
                        elif word >> 48 == 0x38f0:
                            for i in range(7):
                                if bits(20, 7) & (1 << i):
                                    predicates[i] = bool(registers[bits(8, 8)] & (1 << i))
                        elif word & 0xfff0000000000000 == 0x5b60000000000000:
                            self.assertEqual(bits(49, 3), 5)
                            self.assertEqual(bits(45, 2), 1)
                            compared = registers[bits(8, 8)] != registers[bits(20, 8)]
                            predicates[bits(3, 3)] = compared or read_predicate(bits(39, 4))
                        else:
                            self.assertEqual(word >> 48, 0x5090)
                            self.assertEqual(bits(24, 2), 0)
                            self.assertEqual(bits(45, 2), 0)
                            a = read_predicate(bits(12, 4))
                            b = read_predicate(bits(29, 4))
                            c = read_predicate(bits(39, 4))
                            for destination, result in ((bits(3, 3), a and b and c),
                                                        (bits(0, 3), not a and b and c)):
                                if destination != 7:
                                    predicates[destination] = result
                    expected = original.copy()
                    expected[(control >> 17) & 7] = ((value != 0 or original[(control >> 4) & 7])
                                                     and original[(control >> 23) & 7])
                    self.assertEqual(predicates, expected, (hex(control), mask, value))

    def test_oot_uniform_multiply_and_signed_source(self):
        for instruction in (
            (0x040474a4, 0x00003c00, 0x0f8e0206, 0x000fc600),
            (0x00037305, 0x80000013, 0x0021f100, 0x000fe200),
            (0x0e0e7819, 0x00000015, 0x00001211, 0x020fe200),
            (0x000573c4, 0, 0x00010200, 0x001e2400),
            (0x04077899, 0x18, 0x08001206, 0x002fc400),
            (0x032b7219, 0x2c, 0x0000122d, 0x000fe200),
        ):
            with self.subTest(instruction=instruction):
                source = self.write("oot-arithmetic.bin", struct.pack(
                    "<4I", *instruction) + NATIVE_EXIT)
                capture = self.write("shader.env", environment(50, 5))
                self.run_cli(source, "--environment", capture, "--cache-version", 50,
                             "--output", self.output)
                self.validate()

    def test_oot_global_reduction_forms(self):
        instructions = (
            (0xff00798e, 9, 0x0c10e704, 0x0021e800),
            (0x0c00098e, 0xfffff007, 0x0010e100, 0x0011e400),
        )
        for instruction in instructions:
            with self.subTest(instruction=instruction):
                source = self.write("oot-reduction.bin", struct.pack(
                    "<4I", *instruction) + NATIVE_EXIT)
                self.run_cli(source, "--lower-only", self.output)
                words = struct.unpack("<" + "Q" * (self.output.stat().st_size // 8),
                                      self.output.read_bytes())
                reduction = next(word for word in words if word >> 51 == 0xebf8000000000000 >> 51)
                self.assertEqual((reduction >> 20) & 7, 3 if instruction[2] == 0x0c10e704 else 0)
                self.assertEqual((reduction >> 28) & 0xfffff,
                                 0 if instruction[2] == 0x0c10e704 else 0xffff0)

    def test_oot_call_proof_accepts_discard_and_ignored_register_writes(self):
        instructions = [
            (0x00107802, 0x30, 0x00000f00, 0),
            (0x1f1f7212, 6, 0x078e3cff, 0),
            (0x00007944, 0x20, 0x03c00000, 0),
            (0x0000095b, 0, 0x03800000, 0),
            (0x0000794d, 0, 0x03800000, 0),
            (0x00027919, 0, 0x00003900, 0),
            (0x02ff7c12, 4, 0x0f80c0ff, 0),
            (0x00067202, 16, 0x00000f00, 0),
            (0x06007950, 0xffffff70, 0x03c3ffff, 0),
        ]
        source = self.write("oot-call.bin", b"".join(struct.pack("<4I", *op) for op in instructions))
        self.run_cli(source, "--lower-only", self.output)
        instructions[1] = (0x00107802, 0, 0x00000f00, 0)
        source.write_bytes(b"".join(struct.pack("<4I", *op) for op in instructions))
        result = self.run_cli(source, "--lower-only", self.output, code=1)
        self.assertEqual(result["error"]["message"], "native call linkage mode")

