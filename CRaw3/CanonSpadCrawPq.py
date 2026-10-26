"""
Exact rational TIFF/CTMD helpers and experimental balanced-trit utilities.

CanonRationalTagPq encodes and decodes GCD-reduced rational pairs for TIFF
rational types 5 and 10 without converting them to floating point.

SpadTernaryFluxStreamPq classifies changes between sequential counts as -1, 0
or +1. That classification discards count magnitudes and cannot reconstruct
original photon counts. Its separate byte-packing helper preserves the trits
exactly, storing up to five radix-3 digits per byte; the trit count must be
carried separately. Coincidence counting compares at most 64 trits per input.

These are mathematical helpers. This module does not implement a Canon SPAD
hardware interface, a CRX wavelet compressor, or CrxSubbandBfp64Pq. No device
validation or lossless raw-frame compression ratio is established here.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from struct import pack, unpack
from typing import List, Sequence, Tuple


def reduce_rational_pq(num: int, den: int) -> Tuple[int, int]:
    """Return exact GCD-reduced (p, q) with q > 0; reject a zero denominator."""
    if den == 0:
        raise ValueError("Rational denominator must be nonzero")
    if den < 0:
        num, den = -num, -den
    g = math.gcd(abs(num), den)
    return (num // g, den // g)


class CanonRationalTagPq:
    """Exact p/q rational decoder/encoder for Canon CR3 TIFF/CTMD tags (types 5 & 10)."""

    TIFF_TYPE_URATIONAL = 5
    TIFF_TYPE_RATIONAL = 10

    @classmethod
    def decode_le_bytes(cls, raw8: bytes, tiff_type: int) -> Tuple[int, int]:
        """Decode a rational tag, raising ValueError for an undefined p/0 value."""
        if len(raw8) < 8:
            raise ValueError(f"Expected at least 8 bytes, got {len(raw8)}")
        if tiff_type == cls.TIFF_TYPE_URATIONAL:
            num, den = unpack("<LL", raw8[:8])
        elif tiff_type == cls.TIFF_TYPE_RATIONAL:
            num, den = unpack("<ll", raw8[:8])
        else:
            raise ValueError(f"Unsupported rational TIFF type: {tiff_type}")
        return reduce_rational_pq(int(num), int(den))

    @classmethod
    def encode_le_bytes(cls, num: int, den: int, signed: bool = True) -> bytes:
        """Encode a reduced rational, raising ValueError for a zero denominator."""
        p, q = reduce_rational_pq(num, den)
        fmt = "<ll" if signed else "<LL"
        return pack(fmt, p, q)


class SpadTernaryFluxStreamPq:
    """
    Experimental count-difference classification and balanced-trit helpers.
    Packing is lossless for trits, not for the original count sequence.
    Coincidence counting uses Python integer masks for at most 64 positions.
    """

    POW3 = (1, 3, 9, 27, 81)

    @classmethod
    def encode_photon_counts_to_trits(
        cls, counts: Sequence[int], deadtime_threshold: int = 1
    ) -> List[int]:
        """
        Classify count differences as {-1, 0, +1}, discarding their magnitudes.
        """
        if not counts:
            return []
        trits: List[int] = [0]
        for i in range(1, len(counts)):
            delta = counts[i] - counts[i - 1]
            if delta > deadtime_threshold:
                trits.append(1)
            elif delta < -deadtime_threshold:
                trits.append(-1)
            else:
                trits.append(0)
        return trits

    @classmethod
    def pack_5trits_per_byte(cls, trits: Sequence[int]) -> bytes:
        """Pack integer trits {-1, 0, +1}; unused high radix-3 digits are zero.

        The caller must retain the trit count for decoding. Booleans and
        noninteger values raise TypeError; integers outside the alphabet
        raise ValueError.
        """
        out = bytearray()
        n = len(trits)
        for i in range(0, n, 5):
            chunk = trits[i : i + 5]
            byte_val = 0
            for idx, t in enumerate(chunk):
                if isinstance(t, bool) or not isinstance(t, int):
                    raise TypeError('Trits must be integers, not booleans')
                if t not in (-1, 0, 1):
                    raise ValueError('Trits must be -1, 0 or 1')
                digit = t + 1  # {-1,0,+1} -> {0,1,2}
                byte_val += digit * cls.POW3[idx]
            out.append(byte_val)
        return bytes(out)

    @classmethod
    def unpack_5trits_per_byte(cls, packed: bytes, num_trits: int) -> List[int]:
        """Decode a canonical bytes/bytearray frame of exactly num_trits trits.

        The count must be a nonnegative integer, excluding bool. The frame
        must contain exactly ceil(num_trits / 5) bytes, each below 243, with
        zero unused high radix-3 digits in its final byte. Invalid types raise
        TypeError; invalid counts, lengths or encodings raise ValueError.
        """
        if isinstance(num_trits, bool) or not isinstance(num_trits, int):
            raise TypeError('Trit count must be an integer, not a boolean')
        if num_trits < 0:
            raise ValueError('Trit count must be nonnegative')
        if not isinstance(packed, (bytes, bytearray)):
            raise TypeError('Packed trits must be bytes or bytearray')
        if len(packed) != (num_trits + 4) // 5:
            raise ValueError('Packed byte length does not match the trit count')
        out: List[int] = []
        for b in packed:
            if b >= 243:
                raise ValueError('Packed byte contains a reserved trit encoding')
            rem = b
            for _ in range(min(5, num_trits - len(out))):
                digit = rem % 3
                rem //= 3
                out.append(digit - 1)
            if rem:
                raise ValueError('Unused high trit digits must be zero')
        return out

    @classmethod
    def coincidence_popcount_64(cls, trits_a: Sequence[int], trits_b: Sequence[int]) -> Tuple[int, int]:
        """
        Compute exact 64-trit bitplane popcount photon coincidence:
        returns (same_polarity_coincidences, total_active_events).
        """
        length = min(len(trits_a), len(trits_b), 64)
        pos_a = neg_a = pos_b = neg_b = 0
        for i in range(length):
            if trits_a[i] > 0:
                pos_a |= 1 << i
            elif trits_a[i] < 0:
                neg_a |= 1 << i
            if trits_b[i] > 0:
                pos_b |= 1 << i
            elif trits_b[i] < 0:
                neg_b |= 1 << i
        same_pol = ((pos_a & pos_b) | (neg_a & neg_b)).bit_count()
        active_union = ((pos_a | neg_a) | (pos_b | neg_b)).bit_count()
        return same_pol, active_union
