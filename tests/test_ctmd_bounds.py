import struct
import unittest
from canon_cr3.cr3_lib import CmtdDataParser

TIFF = b'II' + struct.pack('<HIH', 42, 8, 0)

def record(payload, kind=7):
    return struct.pack('<LH', 12 + len(payload), kind) + bytes(6) + payload

def parse(data, declared=None):
    obj = CmtdDataParser.__new__(CmtdDataParser)
    obj.cr3 = {'trak4': {b'co64': 0}, b'CTMD': declared or [(7, len(data))]}
    obj._trak_data = lambda _: data
    obj.S_IFD_ENTRY_REC = struct.Struct('<HHLL')
    return obj.parseCTMD()

class TestCtmdBounds(unittest.TestCase):
    def test_zero_payload_does_not_loop(self):
        with self.assertRaises(ValueError):
            parse(record(struct.pack('<LL', 0, 1) + b'ab'))

    def test_payload_sizes_and_headers_rejected(self):
        for size in (1, 7, 100, 2**32 - 1):
            with self.subTest(size=size), self.assertRaises(ValueError):
                parse(record(struct.pack('<LL', size, 1)))
        for length in range(1, 8):
            with self.subTest(length=length), self.assertRaises(ValueError):
                parse(record(bytes(length)))

    def test_record_boundaries_and_mismatch_rejected(self):
        for data, declared in [(bytes(5), [(7, 5)]), (record(b''), [(7, 13)]), (record(b''), [(8, 12)]), (record(b''), [(7, 11)]), (struct.pack('<LH', 6, 7), [(7, 6)])]:
            with self.subTest(data=data, declared=declared), self.assertRaises(ValueError):
                parse(data, declared)

    def test_valid_multiple_payloads_preserve_boundaries(self):
        payload = b''.join(struct.pack('<LL', 8 + len(TIFF), tag) + TIFF for tag in (1, 2))
        out = parse(record(payload))
        self.assertEqual(set(out[7][3]), {1, 2})
        self.assertEqual(out[7][3][1][0], 12)
        self.assertEqual(out[7][3][2][0], 12 + 8 + len(TIFF))
        self.assertEqual(out[7][3][1][3], (0, {}))

    def test_empty_payload_record_and_other_type(self):
        self.assertEqual(parse(record(b''))[7][3], {})
        data = record(b'', 1)
        self.assertEqual(parse(data, [(1, len(data))])[1], (len(data), 1, 0))
