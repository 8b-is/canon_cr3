import struct
import unittest

from canon_cr3.cr3_lib import Cr3FileParser


def box(kind=b'free', payload=b''):
    return struct.pack('>I4s', 8 + len(payload), kind) + payload


def parser():
    obj = Cr3FileParser.__new__(Cr3FileParser)
    obj.count = {}
    obj.cr3 = {}
    obj.tags = {}
    obj.innerOffsets = {}
    obj.SIZELEN = obj.NAMELEN = 4
    obj.UUID_LEN = 16
    return obj


class TestBoxBounds(unittest.TestCase):
    def test_zero_length_top_level_consumes_remaining_data(self):
        for prefix in (b'', box()):
            data = prefix + struct.pack('>I4s', 0, b'free') + b'payload'
            with self.subTest(prefix=len(prefix)):
                self.assertEqual(parser()._parse(data, 0, 0), len(data))

    def test_nested_zero_length_rejected(self):
        with self.assertRaises(ValueError):
            parser()._parse(box(b'moov', struct.pack('>I4s', 0, b'free')), 0, 0)

    def test_short_normal_headers_rejected(self):
        for length in range(1, 8):
            with self.subTest(length=length), self.assertRaises(ValueError):
                parser()._parse(bytes(length), 0, 0)

    def test_sizes_smaller_than_header_rejected(self):
        for length in range(2, 8):
            with self.subTest(length=length), self.assertRaises(ValueError):
                parser()._parse(struct.pack('>I4s', length, b'free'), 0, 0)

    def test_oversized_box_rejected(self):
        for length in (9, 100, 2**32 - 1):
            with self.subTest(length=length), self.assertRaises(ValueError):
                parser()._parse(struct.pack('>I4s', length, b'free'), 0, 0)

    def test_short_extended_header_rejected(self):
        for extra in range(8):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                parser()._parse(struct.pack('>I4s', 1, b'free') + bytes(extra), 0, 0)

    def test_extended_size_bounds(self):
        for length in (0, 1, 8, 15, 17, 2**64 - 1):
            with self.subTest(length=length), self.assertRaises(ValueError):
                parser()._parse(struct.pack('>I4sQ', 1, b'free', length), 0, 0)
        self.assertEqual(parser()._parse(struct.pack('>I4sQ', 1, b'free', 16), 0, 0), 16)

    def test_nested_and_adjacent_valid_boxes(self):
        data = box() + box(b'moov', box() + box(b'moov', box())) + box()
        obj = parser()
        self.assertEqual(obj._parse(data, 0, 0), len(data))
        self.assertEqual(obj.count[b'free'], 4)

    def test_truncated_child_and_trailing_bytes_rejected(self):
        for data in (box() + b'x', box(b'moov', b'abc'), box(b'moov', struct.pack('>I4s', 12, b'free'))):
            with self.subTest(data=data), self.assertRaises(ValueError):
                parser()._parse(data, 0, 0)

    def test_uuid_headers_rejected_when_truncated(self):
        for length in range(16):
            with self.subTest(length=length), self.assertRaises(ValueError):
                parser()._parse(box(b'uuid', bytes(length)), 0, 0)
        known = bytes.fromhex('eaf42b5e1c984b88b9fbb7dc406e4d16')
        with self.assertRaises(ValueError):
            parser()._parse(box(b'uuid', known), 0, 0)

    def test_container_prefix_cannot_exceed_payload(self):
        obj = parser()
        obj.innerOffsets[b'test'] = 12
        with self.assertRaises(ValueError):
            obj._parse(box(b'test', bytes(11)), 0, 0)

    def test_excessive_nesting_rejected(self):
        data = box()
        for _ in range(130):
            data = box(b'moov', data)
        with self.assertRaises(ValueError):
            parser()._parse(data, 0, 0)

    def test_empty_stream_and_empty_container(self):
        self.assertEqual(parser()._parse(b'', 0, 0), 0)
        self.assertEqual(parser()._parse(box(b'moov'), 0, 0), 8)
