"""Canonical framing and alphabet checks for the experimental trit helpers."""
import itertools
import unittest

from CRaw3.CanonSpadCrawPq import SpadTernaryFluxStreamPq as Codec


class TestTritFraming(unittest.TestCase):
    def test_pack_rejects_values_outside_the_trit_alphabet(self):
        for value in (-100, -2, 2, 100):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Codec.pack_5trits_per_byte([0, value, 1])

    def test_pack_rejects_noninteger_trits(self):
        for value in (True, False, 1.0, -1.0, float('nan'), '1', None):
            with self.subTest(value=value), self.assertRaises(TypeError):
                Codec.pack_5trits_per_byte([value])

    def test_unpack_requires_nonnegative_integer_count(self):
        for count in (-1, -5):
            with self.subTest(count=count), self.assertRaises(ValueError):
                Codec.unpack_5trits_per_byte(b'', count)
        for count in (True, False, 1.0, 1.5, '1', None):
            with self.subTest(count=count), self.assertRaises(TypeError):
                Codec.unpack_5trits_per_byte(b'\x00', count)

    def test_unpack_requires_bytes_or_bytearray(self):
        for data in ([0], (0,), '0'):
            with self.subTest(data=data), self.assertRaises(TypeError):
                Codec.unpack_5trits_per_byte(data, 1)
        self.assertEqual(Codec.unpack_5trits_per_byte(bytearray([0]), 1), [-1])

    def test_unpack_rejects_missing_and_extra_bytes(self):
        for data, count in ((b'', 1), (b'', 5), (b'\x00', 6),
                            (b'\x00', 0), (b'\x00\x00', 1),
                            (b'\x00\x00', 5), (b'', 10**100)):
            with self.subTest(data=data, count=count), self.assertRaises(ValueError):
                Codec.unpack_5trits_per_byte(data, count)

    def test_reserved_bytes_cannot_alias_valid_trits(self):
        for value in range(243, 256):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Codec.unpack_5trits_per_byte(bytes([value]), 5)
        with self.assertRaises(ValueError):
            Codec.unpack_5trits_per_byte(bytes([121, 243]), 10)

    def test_unused_high_digits_must_be_zero(self):
        for count in range(1, 5):
            for value in range(3**count, 243):
                with self.subTest(count=count, value=value), self.assertRaises(ValueError):
                    Codec.unpack_5trits_per_byte(bytes([value]), count)
        with self.assertRaises(ValueError):
            Codec.unpack_5trits_per_byte(bytes([121, 3]), 6)

    def test_all_valid_patterns_and_multibyte_vectors_roundtrip(self):
        for length in range(6):
            for trits in itertools.product((-1, 0, 1), repeat=length):
                encoded = Codec.pack_5trits_per_byte(trits)
                with self.subTest(trits=trits):
                    self.assertEqual(Codec.unpack_5trits_per_byte(encoded, length), list(trits))
        for length in (6, 9, 10, 11, 64, 65):
            trits = [(-1, 0, 1)[i % 3] for i in range(length)]
            self.assertEqual(Codec.unpack_5trits_per_byte(Codec.pack_5trits_per_byte(trits), length), trits)

    def test_wire_examples_and_count_transform_limit(self):
        for trits, encoded in (([-1]*5, b'\x00'), ([0]*5, b'\x79'),
                               ([1]*5, b'\xf2'), ([-1, 0, 1], b'\x15'),
                               ([], b'')):
            with self.subTest(trits=trits):
                self.assertEqual(Codec.pack_5trits_per_byte(trits), encoded)
                self.assertEqual(Codec.unpack_5trits_per_byte(encoded, len(trits)), trits)
        # Packing preserves trits, but the preceding count transform is lossy.
        self.assertEqual(Codec.encode_photon_counts_to_trits([10, 20]), [0, 1])
        self.assertEqual(Codec.encode_photon_counts_to_trits([100, 200]), [0, 1])
