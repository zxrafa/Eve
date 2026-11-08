import hashlib
import struct

from .nup_fixtures import fixture


class NupExtraCases:
    def test_input_outside_library_is_rejected(self):
        outside = self.root / "outside.nup"
        outside.write_bytes(self.data)
        self.run_export(success=False, source=outside)

    def test_unsafe_member_names_are_rejected(self):
        for index, name in enumerate([
            "../escape.bfsha", "bad:stream.bfsha", "CON.bfsha", "back\\\\slash.bfsha",
            "COM\u00b9.bfsha", "CONOUT$.bfsha",
        ]):
            with self.subTest(name=name):
                source = self.library / f"unsafe-{index}.nup"
                source.write_bytes(fixture(filename=name)[0])
                manifest, output = self.run_export(success=False, source=source)
                self.assertEqual(manifest["status"], "error")
                self.assertFalse((output / "packages").exists())
        self.assertFalse((self.root / "escape.bfsha").exists())

    def test_unicode_name_is_preserved(self):
        source = self.library / "unicode.nup"
        source.write_bytes(fixture(filename="シェーダー.bfsha")[0])
        _, output = self.run_export(["--path", "0:/Shaders/シェーダー.bfsha"], source=source)
        self.assertEqual((output / "packages/0/romfs/Shaders/シェーダー.bfsha").read_bytes(),
                         self.payloads[0])

    def test_corrupt_zstd_is_not_read_by_catalog_but_fails_export(self):
        source = self.library / "broken.nup"
        source.write_bytes(fixture(corrupt=True)[0])
        self.run_export(source=source)
        manifest, output = self.run_export(
            ["--path", "0:/Shaders/Shader.bfsha"], source=source, success=False)
        self.assertEqual(manifest["status"], "error")
        self.assertIn("decompression", manifest["error"])
        self.assertFalse((output / "packages/0/romfs/Shaders/Shader.bfsha").exists())
        self.assertEqual(list((output / "spill").iterdir()), [])

    def test_corrupt_toc_is_rejected(self):
        source = self.library / "bad-toc.nup"
        data = bytearray(self.data)
        data[0x18] ^= 1
        source.write_bytes(data)
        manifest, _ = self.run_export(source=source, success=False)
        self.assertIn("parse failed", manifest["error"])

    def test_metadata_allocation_limit(self):
        source = self.library / "oversized-toc.nup"
        header = bytearray(self.data[:0x80])
        size = 256 * 1024 * 1024 + 1
        blob = (0x80 + size + 15) & ~15
        struct.pack_into("<Q", header, 0x10, size)
        struct.pack_into("<Q", header, 0x38, blob)
        struct.pack_into("<Q", header, 0x40, blob)
        with source.open("wb") as stream:
            stream.write(header)
            stream.truncate(blob)
        manifest, _ = self.run_export(source=source, success=False)
        self.assertIn("metadata exceeds", manifest["error"])

    def test_no_candidate_matches_is_not_empty_success(self):
        source = self.library / "no-candidates.nup"
        data = bytearray(fixture(filename="payload.data")[0])
        toc_end = 0x80 + struct.unpack_from("<Q", data, 0x10)[0]
        toc = data[0x80:toc_end].replace(b"Shaders", b"AssetsX").replace(b"empty.bnsh", b"empty.data")
        data[0x80:toc_end] = toc
        data[0x18:0x38] = hashlib.sha256(toc).digest()
        source.write_bytes(data)
        manifest, _ = self.run_export(["--candidates"], source=source, success=False)
        self.assertIn("No files matched", manifest["error"])

