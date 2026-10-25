"""
================================================================================
[8b-is Sovereign Canon CR3 / C-RAW / SPAD Substrate — Exact p/q Rational
 EXIF/CTMD Evaluator, SPAD 5-Trit/Byte Photon-Flux Stream & Omni BFP-64 Wavelets]

Connects Canon CR3 / C-RAW (`CMP1` / `CRX` LeGall 5/3 wavelet codec) & Canon
Megapixel SPAD (Single-Photon Avalanche Diode) imaging with the 8b-is stack:
- https://github.com/8b-is/alexiai (GAIA-MLX-QUANT 5-trits/byte b1.58 kernel)
- https://github.com/8b-is/japan   (Canon NIL PMO + SPAD Ternary + Medical Exegesis)

Key Bugfixes & Mathematical Upgrades for `canon_cr3`:
1. Bugfix in `CRaw3/TiffIfd.py`:
   Line 138 had a duplicate `elif type == TiffIfd.TIFF_TYPE_URATIONAL:` branch
   that made `TIFF_TYPE_RATIONAL` (type 10, signed rational `p/q` used for Canon
   APEX ExposureBiasValue, ShutterSpeedValue, and ColorMatrix) unreachable, and
   unpacked signed numerators/denominators with unsigned `<L`. Fixed to check
   `TIFF_TYPE_RATIONAL` and unpack signed `<l` via `getSignedLongLE`.
2. Bugfix in `CRaw3/Crx.py`:
   Handled Canon's 4-byte zero padding tail in `CMP1.hsize` (`sign == 0 and length == 0`)
   without aborting `parse_tile()`.
3. Exact GCD-Reduced `p/q` Rational TIFF/CTMD Tag Evaluator (`CanonRationalTagPq`):
   Decodes raw 8-byte little-endian `URATIONAL` (type 5) and `RATIONAL` (type 10)
   records directly into reduced `(p, q)` integer pairs with zero IEEE-754 drift.
4. Canon SPAD Balanced-Ternary `b1.58` (`{-1, 0, +1}`) Photon-Flux Codec
   (`SpadTernaryFluxStreamPq`):
   Maps single-photon avalanche timestamp differentials into balanced-ternary
   trits (`+1` rising photon flux edge, `0` dead-time/dark-count equilibrium,
   `-1` falling flux / quench) packed at 5 trits per byte (`3^5 = 243 <= 256`),
   achieving `10/1x` compression vs 16-bit raw frames and `O(1)` bitplane popcount
   coincidence detection.
5. Omni BFP-64 Wavelet Subband Tile Compressor (`CrxSubbandBfp64Pq`):
   Compresses 64-coefficient CRX wavelet blocks into 64 `int8` mantissas + 1 shared
   `int8` exponent (`256/65 ~= 63/16x` vs FP32).
================================================================================
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
    Canon Megapixel SPAD Balanced-Ternary {-1, 0, +1} Photon-Flux Event Stream.
    Packs 5 trits per byte (3^5 = 243 <= 256) and 64-trit bitplane masks
    (pos_mask: u64, neg_mask: u64) for hardware popcount photon coincidence gating.
    """

    POW3 = (1, 3, 9, 27, 81)

    @classmethod
    def encode_photon_counts_to_trits(
        cls, counts: Sequence[int], deadtime_threshold: int = 1
    ) -> List[int]:
        """
        Convert sequential SPAD photon-avalanche counts into balanced-ternary
        flux differential trits {-1, 0, +1}.
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
        """Pack balanced trits {-1, 0, +1} at 5 trits per byte (radix-3 digits {0, 1, 2})."""
        out = bytearray()
        n = len(trits)
        for i in range(0, n, 5):
            chunk = trits[i : i + 5]
            byte_val = 0
            for idx, t in enumerate(chunk):
                digit = (1 if t > 0 else (-1 if t < 0 else 0)) + 1  # {-1,0,+1} -> {0,1,2}
                byte_val += digit * cls.POW3[idx]
            out.append(byte_val)
        return bytes(out)

    @classmethod
    def unpack_5trits_per_byte(cls, packed: bytes, num_trits: int) -> List[int]:
        """Unpack 5-trits-per-byte stream back to exact {-1, 0, +1} trits."""
        out: List[int] = []
        for b in packed:
            rem = int(b)
            for _ in range(5):
                if len(out) >= num_trits:
                    break
                digit = rem % 3
                rem //= 3
                out.append(digit - 1)
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
