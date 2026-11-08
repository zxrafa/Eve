import struct

from .cli_fixtures import NATIVE_EXIT, STAGES, environment, header, spirv_instructions


class CoreCliCases:
    def test_instruction_only_requires_stage(self):
        source = self.write("native.bin", NATIVE_EXIT)
        self.run_cli(source, "--output", self.output, code=2)
        self.assertFalse(self.output.exists())

    def test_graphics_requires_header_or_environment(self):
        source = self.write("native.bin", NATIVE_EXIT)
        result = self.run_cli(source, "--stage", "vertex", "--output", self.output, code=1)
        self.assertEqual(result["phase"], "context")
        self.assertFalse(self.output.exists())

    def test_compute_offline_assumptions(self):
        source = self.write("native.bin", NATIVE_EXIT)
        result = self.run_cli(source, "--stage", "compute", "--output", self.output)
        self.assertTrue(any("workgroup 1x1x1" in item for item in result["assumptions"]))
        self.validate()

    def test_exact_native_header_stages(self):
        for stage, name in enumerate(STAGES[:5]):
            with self.subTest(stage=name):
                source = self.write("header.bin", header(stage) + bytes(48) + NATIVE_EXIT)
                result = self.run_cli(source, "--format", "native-header", "--output", self.output)
                self.assertEqual(result["stage"], name)
                models = [args[0] for op, args in spirv_instructions(self.output.read_bytes()) if op == 15]
                self.assertEqual(models, [stage])
                self.validate()

    def test_header_stage_mismatch(self):
        source = self.write("header.bin", header(0) + bytes(48) + NATIVE_EXIT)
        self.run_cli(source, "--format", "native-header", "--stage", "fragment", "--output", self.output, code=2)

    def test_geometry_return_before_exit_handler(self):
        instructions = (
            (0x0000734e, 0, 0, 0),
            (0x00037802, 0xe0, 0x00000f00, 0),
            (0x00007210, 3, 0x07f1e0ff, 0),
            (0xff017224, 0xff, 0x000e0401, 0),
            (0x00007357, 0, 0, 0),
            (0x00007802, 0, 0x00000f00, 0),
            (0x00017802, 0, 0x00000f00, 0),
            (0x00037802, 0, 0x00000f00, 0),
            (0x0100720c, 0xff, 0x03f03070, 0),
            (0x00087802, 0xb0, 0x00000f00, 0),
            (0x00007944, 0x10, 0x03c00000, 0),
            (0x0000794d, 0, 0x03800000, 0),
            (0x00007324, 0xff, 0x00004000, 0),
            (0x08007950, 0xffffff20, 0x03c3ffff, 0),
            (0x00ff7324, 0xff, 0, 0),
            (0x00007957, 0, 0, 0),
            (0x0000794d, 0, 0x03800000, 0),
        )
        source = self.write("geometry-call.bin", header(3) + bytes(48) +
                            b"".join(struct.pack("<4I", *op) for op in instructions))
        self.run_cli(source, "--format", "native-header", "--output", self.output)
        self.validate()
        emitted = list(spirv_instructions(self.output.read_bytes()))
        self.assertEqual(sum(op == 218 for op, _ in emitted), 1)

    def test_both_cache_versions_all_stages(self):
        for version in (46, 47, 48, 49, 50, 51, 52):
            for stage, name in enumerate(STAGES):
                with self.subTest(version=version, stage=name):
                    capture = self.write("shader.env", environment(version, stage))
                    result = self.run_cli("--environment", capture, "--cache-version", version, "--output", self.output)
                    self.assertEqual(result["stage"], name)
                    models = [args[0] for op, args in spirv_instructions(self.output.read_bytes()) if op == 15]
                    self.assertEqual(models, [stage])
                    self.validate()

    def test_raw_overlay(self):
        capture = self.write("shader.env", environment(47, 4))
        source = self.write("native.bin", NATIVE_EXIT)
        result = self.run_cli(source, "--environment", capture, "--cache-version", 47, "--output", self.output)
        self.assertEqual(result["stage"], "fragment")
        self.validate()

    def test_surface_pixel_format_outside_shader_enum(self):
        for version in (46, 47, 48):
            with self.subTest(version=version):
                capture = self.write("shader.env", environment(version, 5, formats=((0, 111),)))
                self.run_cli("--environment", capture, "--cache-version", version, "--output", self.output)
                self.validate()

    def test_pixel_format_exceeds_serialized_domain(self):
        capture = self.write("shader.env", environment(47, 5, formats=((0, 256),)))
        result = self.run_cli("--environment", capture, "--cache-version", 47, "--output", self.output, code=2)
        self.assertEqual(result["error"]["message"], "Invalid texture pixel format")

    def test_truncated_records_and_trailing_data(self):
        full = environment(47, 3)
        for size in range(len(full)):
            capture = self.write("shader.env", full[:size])
            self.run_cli("--environment", capture, "--cache-version", 47, "--output", self.output, code=2)
        capture = self.write("shader.env", full + b"x")
        self.run_cli("--environment", capture, "--cache-version", 47, "--output", self.output, code=2)

    def test_invalid_lengths_versions_and_opcode(self):
        for data in (b"", NATIVE_EXIT[:-1], NATIVE_EXIT + b"x"):
            source = self.write("native.bin", data)
            self.run_cli(source, "--lower-only", self.output, code=2)
        capture = self.write("shader.env", environment(46, 5))
        self.run_cli("--environment", capture, "--cache-version", 50, "--output", self.output, code=2)
        source = self.write("native.bin", bytes(16))
        result = self.run_cli(source, "--lower-only", self.output, code=1)
        self.assertEqual(result["phase"], "lower")
        self.assertEqual(result["error"]["offset"], 0)

