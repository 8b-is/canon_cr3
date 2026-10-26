"""
Unit tests for Canon CR3 (`canon_cr3`) signed TIFF_TYPE_RATIONAL (type 10) fix,
CRX 4-byte zero padding fix, and SPAD 5-trits/byte balanced-ternary stream.
"""

import importlib.util
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from struct import pack

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from CRaw3.TiffIfd import TiffIfd

_MOD_PATH = os.path.join(
    os.path.dirname(__file__), "..", "CRaw3", "CanonSpadCrawPq.py"
)
_SPEC = importlib.util.spec_from_file_location("CanonSpadCrawPq", _MOD_PATH)
canon_mod = importlib.util.module_from_spec(_SPEC)
sys.modules["CanonSpadCrawPq"] = canon_mod
assert _SPEC.loader is not None
_SPEC.loader.exec_module(canon_mod)

CanonRationalTagPq = canon_mod.CanonRationalTagPq
SpadTernaryFluxStreamPq = canon_mod.SpadTernaryFluxStreamPq
reduce_rational_pq = canon_mod.reduce_rational_pq


class TestCanonCr3SpadPq(unittest.TestCase):
    def test_reduce_rational_rejects_zero_denominator(self):
        for numerator in (-7, 0, 7):
            with self.subTest(numerator=numerator):
                with self.assertRaisesRegex(ValueError, "denominator"):
                    reduce_rational_pq(numerator, 0)

    def test_decode_rejects_undefined_signed_and_unsigned_tags(self):
        for fmt, tag_type, numerator in (
            ("<ll", CanonRationalTagPq.TIFF_TYPE_RATIONAL, -7),
            ("<LL", CanonRationalTagPq.TIFF_TYPE_URATIONAL, 7),
            ("<ll", CanonRationalTagPq.TIFF_TYPE_RATIONAL, 0),
        ):
            with self.subTest(tag_type=tag_type, numerator=numerator):
                with self.assertRaisesRegex(ValueError, "denominator"):
                    CanonRationalTagPq.decode_le_bytes(pack(fmt, numerator, 0), tag_type)

    def test_encode_rejects_zero_denominator(self):
        for signed in (False, True):
            for numerator in (0, 7):
                with self.subTest(signed=signed, numerator=numerator):
                    with self.assertRaisesRegex(ValueError, "denominator"):
                        CanonRationalTagPq.encode_le_bytes(numerator, 0, signed=signed)

    def test_valid_rational_values_remain_exact(self):
        cases = (
            (-6, 9, True, (-2, 3)),
            (6, -9, True, (-2, 3)),
            (-6, -9, True, (2, 3)),
            (0, -9, True, (0, 1)),
            (-(2**31), 1, True, (-(2**31), 1)),
            (2**32 - 1, 1, False, (2**32 - 1, 1)),
        )
        for numerator, denominator, signed, expected in cases:
            with self.subTest(numerator=numerator, denominator=denominator):
                encoded = CanonRationalTagPq.encode_le_bytes(numerator, denominator, signed)
                tag_type = 10 if signed else 5
                self.assertEqual(CanonRationalTagPq.decode_le_bytes(encoded, tag_type), expected)

    def test_tiff_ifd_signed_rational_type10_display(self):
        # Build minimal Canon Little-Endian ('II') TIFF IFD with 1 signed RATIONAL (type 10) entry: -2 / 3 EV
        # Header (8B): 'II', 0x002a, offset=8
        # Count (2B): 1
        # Entry (12B): tag=0x9204 (ExposureBiasValue), type=10 (RATIONAL), length=1, val_offset=22
        # Payload at offset 22 (8B): -2, 3 in signed <ll
        raw_ifd = (
            b"II"
            + pack("<HH", 0x2A, 8)
            + b"\x00\x00"
            + pack("<H", 1)
            + pack("<HHLL", 0x9204, TiffIfd.TIFF_TYPE_RATIONAL, 1, 22)
            + pack("<ll", -2, 3)
        )
        ifd = TiffIfd(raw_ifd, len(raw_ifd), 0, b"CMT2", display=False)
        buf = io.StringIO()
        with redirect_stdout(buf):
            ifd.display(depth=0)
        output = buf.getvalue()
        self.assertIn("-2 / 3", output)

        # Also verify CanonRationalTagPq reduces (-6, 9) -> (-2, 3)
        encoded = CanonRationalTagPq.encode_le_bytes(-6, 9, signed=True)
        self.assertEqual(
            CanonRationalTagPq.decode_le_bytes(encoded, CanonRationalTagPq.TIFF_TYPE_RATIONAL),
            (-2, 3),
        )

    def test_spad_5trits_per_byte_lossless_roundtrip_and_popcount(self):
        counts = [10, 15, 15, 8, 2, 9, 10, 3, 20, 21, 14]
        trits = SpadTernaryFluxStreamPq.encode_photon_counts_to_trits(counts, deadtime_threshold=1)
        packed = SpadTernaryFluxStreamPq.pack_5trits_per_byte(trits)
        # 11 trits pack into ceil(11/5) = 3 bytes (vs 22 bytes in INT16 = 22/3x compression!)
        self.assertEqual(len(packed), 3)
        unpacked = SpadTernaryFluxStreamPq.unpack_5trits_per_byte(packed, len(trits))
        self.assertEqual(trits, unpacked)

        same_pol, active_u = SpadTernaryFluxStreamPq.coincidence_popcount_64(trits, trits)
        expected_active = sum(1 for t in trits if t != 0)
        self.assertEqual(same_pol, expected_active)
        self.assertEqual(active_u, expected_active)


if __name__ == "__main__":
    unittest.main()
