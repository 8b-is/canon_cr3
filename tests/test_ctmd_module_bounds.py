"""Bounds checks for the CRaw3 parser used by the command line."""
import struct
import subprocess
import sys
import unittest
from pathlib import Path

from CRaw3.Ctmd import Ctmd


TIFF = b'II' + struct.pack('<HIH', 42, 8, 0)


def payload(tag=1, tiff=TIFF):
    return struct.pack('<LL', 8 + len(tiff), tag) + tiff


def record(body=b'', kind=7):
    return struct.pack('<LHBBHH', 12 + len(body), kind, 0, 0, 0, 0) + body


def parser(index, offsets, sizes):
    data = struct.pack('>LLL', 0, 0, len(index))
    data += b''.join(struct.pack('>HHL', 0, kind, size) for kind, size in index)
    obj = Ctmd(data, len(data), 0, b'CTMD')
    obj.offsets, obj.sizes = offsets, sizes
    return obj


def parse(data, index=None, offsets=None, sizes=None):
    return parser(index if index is not None else [(7, len(data))],
                  [0] if offsets is None else offsets,
                  [len(data)] if sizes is None else sizes).parse(data)


class TestCtmdModuleBounds(unittest.TestCase):
    def test_zero_payload_cannot_hang(self):
        source = """
from test_ctmd_module_bounds import parse, record, TIFF
import struct
parse(record(struct.pack('<LL', 0, 1) + TIFF))
"""
        root = Path(__file__).resolve().parents[1]
        source = 'import sys; sys.path.insert(0, "tests")\n' + source
        result = subprocess.run([sys.executable, '-c', source], cwd=root,
                                capture_output=True, text=True, timeout=2)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ValueError', result.stderr)

    def test_index_header_and_count_bounds(self):
        for data in (b'', bytes(11), struct.pack('>LLL', 0, 0, 1),
                     struct.pack('>LLL', 0, 0, 2**32 - 1) + bytes(8)):
            with self.subTest(data=data), self.assertRaises(ValueError):
                Ctmd(data, len(data), 0, b'CTMD')

    def test_picture_ranges_and_count_mismatch(self):
        data = record()
        for offsets, sizes in (([-1], [12]), ([0], [-1]), ([1], [12]),
                               ([13], [0]), ([0], [13]), ([0, 0], [12]),
                               ([0], [12, 12])):
            with self.subTest(offsets=offsets, sizes=sizes), self.assertRaises(ValueError):
                parse(data, offsets=offsets, sizes=sizes)

    def test_record_headers_and_index_mismatch(self):
        for data, index in ((bytes(11), [(7, 11)]), (record(), [(7, 13)]),
                            (record(), [(8, 12)]), (record(), [(7, 11)]),
                            (record(), [(7, 0)]),
                            (struct.pack('<L', 13) + record()[4:], [(7, 12)])):
            with self.subTest(index=index, data=data), self.assertRaises(ValueError):
                parse(data, index)

    def test_payload_size_bounds(self):
        for size in (1, 7, 27, 2**32 - 1):
            with self.subTest(size=size), self.assertRaises(ValueError):
                parse(record(struct.pack('<LL', size, 1) + TIFF))

    def test_truncated_payload_headers(self):
        for length in range(1, 8):
            with self.subTest(length=length), self.assertRaises(ValueError):
                parse(record(bytes(length)))

    def test_known_scalar_record_minimums(self):
        for kind, size in ((1, Ctmd.S_CTMD_TIMESTAMP.size),
                           (4, Ctmd.S_CTMD_FOCAL.size),
                           (5, Ctmd.S_CTMD_EXPOSURE.size)):
            data = record(bytes(size - 1), kind)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                parse(data, [(kind, len(data))])

    def test_tiff_cannot_read_following_payload(self):
        # The first TIFF declares an entry but has none. Its parser must not
        # borrow the next payload header and TIFF bytes as that entry.
        truncated = b'II' + struct.pack('<HIH', 42, 8, 1)
        with self.assertRaises(struct.error):
            parse(record(payload(1, truncated) + payload(2)))

    def test_valid_payloads_and_picture_offsets(self):
        data = record(payload(1) + payload(2))
        combined = b'prefix' + data + data
        out = parse(combined, [(7, len(data))], [6, 6 + len(data)],
                    [len(data), len(data)])
        self.assertEqual(list(out), [0, 1])
        for picture, start in ((0, 6), (1, 6 + len(data))):
            entry = out[picture][7]
            self.assertEqual(entry.offset, start)
            self.assertEqual(set(entry.content), {1, 2})
            for tag, offset in ((1, 12), (2, 12 + len(payload()))):
                item = entry.content[tag]
                self.assertEqual(item[:3], (start + offset, len(payload()), tag))
                self.assertEqual(item[3][1].base, start + offset + 8)
                self.assertEqual(item[3][1].ifd, {})

    def test_valid_scalars_and_unknown_records(self):
        bodies = [(1, struct.pack('<HHBBBBBB', 0, 2026, 10, 26, 9, 30, 0, 5)),
                  (4, struct.pack('<HH', 50, 1)),
                  (5, struct.pack('<HHHHL', 4, 1, 1, 200, 100)),
                  (99, b'opaque')]
        data = b''.join(record(body, kind) for kind, body in bodies)
        index = [(kind, 12 + len(body)) for kind, body in bodies]
        out = parse(data, index)[0]
        self.assertEqual(out[1].content, (2026, 10, 26, 9, 30, 0, 5))
        self.assertEqual(out[4].content, (50, 1))
        self.assertEqual(out[5].content, (4, 1, 1, 200, 100))
        self.assertIsNone(out[99].content)
        self.assertEqual(parse(record())[0][7].content, {})
