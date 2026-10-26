"""Exercise the actual command-line parser with bounded subprocesses."""
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'parse_cr3.py'


def box(kind=b'free', payload=b''):
    return struct.pack('>I4s', 8 + len(payload), kind) + payload


FTYP = box(b'ftyp', b'crx ' + bytes(4))


class TestCliBoxBounds(unittest.TestCase):
    def run_cli(self, tail):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'input.cr3'
            path.write_bytes(FTYP + tail)
            return subprocess.run(
                [sys.executable, str(CLI), '-q', str(path)],
                cwd=folder, capture_output=True, text=True, timeout=2,
            )

    def assert_rejected(self, tail):
        result = self.run_cli(tail)
        self.assertNotEqual(result.returncode, 0, 'Malformed input was accepted')
        self.assertIn('ValueError', result.stderr)

    def test_zero_size_top_level_consumes_remainder(self):
        result = self.run_cli(struct.pack('>I4s', 0, b'free') + b'opaque tail')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_nested_zero_size_rejected(self):
        self.assert_rejected(box(b'moov', struct.pack('>I4s', 0, b'free')))

    def test_normal_size_bounds(self):
        for size in (2, 7, 9, 100, 2**32 - 1):
            with self.subTest(size=size):
                self.assert_rejected(struct.pack('>I4s', size, b'free'))

    def test_truncated_normal_headers(self):
        for length in range(1, 8):
            with self.subTest(length=length):
                self.assert_rejected(bytes(length))

    def test_truncated_extended_headers(self):
        for length in (0, 4, 7):
            with self.subTest(length=length):
                self.assert_rejected(struct.pack('>I4s', 1, b'free') + bytes(length))

    def test_extended_size_bounds(self):
        for size in (0, 8, 15, 17, 2**64 - 1):
            with self.subTest(size=size):
                self.assert_rejected(struct.pack('>I4sQ', 1, b'free', size))
        result = self.run_cli(struct.pack('>I4sQ', 1, b'free', 16))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_child_cannot_consume_parent_sibling(self):
        child = struct.pack('>I4s', 16, b'free')
        self.assert_rejected(box(b'moov', child) + box())

    def test_uuid_and_container_prefix_bounds(self):
        for length in (0, 15):
            with self.subTest(uuid_length=length):
                self.assert_rejected(box(b'uuid', bytes(length)))
        preview_uuid = bytes.fromhex('eaf42b5e1c984b88b9fbb7dc406e4d16')
        self.assert_rejected(box(b'uuid', preview_uuid + bytes(7)))
        for kind, length in ((b'CCTP', 11), (b'stsd', 7), (b'dref', 7), (b'CDI1', 3)):
            with self.subTest(kind=kind):
                self.assert_rejected(box(kind, bytes(length)))

    def test_valid_nested_adjacent_and_uuid_boxes(self):
        containers = [bytes.fromhex(value) for value in (
            '85c0b687820f11e08111f4ce462b6a48',
            '5766b829bb6a47c5bcfb8b9f2260d06d',
            '210f1687914911e4811100242131fce4',
        )]
        tail = box() + box(b'moov', box() + box(b'moov'))
        tail += b''.join(box(b'uuid', value + box()) for value in containers)
        tail += box(b'CCTP', bytes(12) + box())
        result = self.run_cli(tail)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_nesting_resource_limit(self):
        tail = box()
        for _ in range(130):
            tail = box(b'moov', tail)
        self.assert_rejected(tail)
