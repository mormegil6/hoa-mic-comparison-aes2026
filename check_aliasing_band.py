#!/usr/bin/env python3
"""
check_aliasing_band.py
======================

Verification: re-compute the per-order RMS for ZM-1 vs Spcmic 3OA but
restrict the calculation to frequency bins below several cut-offs. The
0->3 rolloff is then compared to the full-band number (\\RolloffZMOneFranck
etc.).

Motivation: the ZM-1's 3rd-order spatial bandwidth (per Pinardi et al. 2021)
is approximately 660-3080 Hz; above ~3 kHz the array is in spatial-aliasing
territory by design. If the headline 19 dB rolloff gap lives mostly above
3 kHz, the paper would be measuring aliasing rather than order-truncation
behaviour. This script answers that.

Usage:
    python check_aliasing_band.py
"""

import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import welch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_paper import DEFAULT_BASE, ORDER_RANGES  # noqa: E402

# Files to check (Aug 15 only - both pieces, ZM-1 + Spcmic 3OA)
FILES = [
    ("ZM-1 Franck",       "2024.08.15 -- ZM1 Spcmic Saramonic", "3OA_ZM1_CFranck-PreludeChoralFugue.wav"),
    ("ZM-1 Prokofiev",    "2024.08.15 -- ZM1 Spcmic Saramonic", "3OA_ZM1_SProkofiev-Sonata4.wav"),
    ("Spcmic 3OA Franck", "2024.08.15 -- ZM1 Spcmic Saramonic", "3OA_Spcmic_CFranck-PreludeChoralFugue.wav"),
    ("Spcmic 3OA Prok.",  "2024.08.15 -- ZM1 Spcmic Saramonic", "3OA_Spcmic_SProkofiev-Sonata4.wav"),
]

CUTOFFS = [None, 5000.0, 3000.0, 2000.0, 1000.0]   # None = full-band
NPERSEG = 8192


def per_channel_band_power(path, fmax, n_channels, n_frames, sr):
    """Stream the file, accumulating Welch PSD per channel, then integrate
    over [0, fmax] (or full band when fmax is None)."""
    # We accumulate (sum of squared FFT magnitudes) per Welch segment; for
    # the band-limited integral we just sum power in [0, fmax] bins.
    # To stay memory-cheap we run welch one channel at a time, reading
    # only that channel via soundfile's column slice.
    powers = np.zeros(n_channels)
    with sf.SoundFile(path) as f:
        # Read everything once (Welch needs full vector). For a 19 min,
        # 48 kHz mono channel this is ~220 MB float32 -- manageable.
        data = f.read(dtype='float32', always_2d=True)
    for ch in range(n_channels):
        freqs, pxx = welch(data[:, ch], fs=sr, nperseg=NPERSEG,
                           noverlap=NPERSEG // 2, window='hann')
        df = freqs[1] - freqs[0]
        if fmax is None:
            mask = slice(None)
        else:
            mask = freqs <= fmax
        powers[ch] = float(np.sum(pxx[mask]) * df)
    return powers


def order_dbfs(powers, n_channels, max_order):
    rms = np.sqrt(powers)
    out = {}
    for order in range(max_order + 1):
        s, e = ORDER_RANGES[order]
        if e <= n_channels:
            avg = float(np.mean(rms[s:e]))
            out[order] = 20.0 * np.log10(avg + 1e-20)
    return out


def main():
    base = DEFAULT_BASE
    if not base.exists():
        sys.exit(f"Source folder not mounted: {base}")

    results = {}   # results[label] = {cutoff: order_dbfs_dict}

    for label, session, fname in FILES:
        path = base / session / "render" / fname
        info = sf.info(path)
        sr, nch, n = info.samplerate, info.channels, info.frames
        max_order = 5 if nch >= 36 else 3 if nch >= 16 else 1
        print(f"[i] {label}: {nch} ch, {n/sr/60:.1f} min, sr={sr}")
        results[label] = {}
        for fmax in CUTOFFS:
            print(f"     cutoff={'full' if fmax is None else f'<{int(fmax)} Hz'} ...")
            p = per_channel_band_power(path, fmax, nch, n, sr)
            results[label][fmax] = order_dbfs(p, nch, max_order)

    # ----- Print rolloff (0->3) per (label, cutoff) -------------------------
    print()
    print("=" * 78)
    print("0 -> 3 rolloff (dB), under different upper-frequency cutoffs")
    print("=" * 78)
    header = f"{'Microphone':<22}" + "".join(
        f"  {'full' if c is None else f'<{int(c)/1000:.0f} kHz':>7}" for c in CUTOFFS
    )
    print(header)
    print("-" * len(header))
    for label in results:
        row = f"{label:<22}"
        for c in CUTOFFS:
            o = results[label][c]
            if 0 in o and 3 in o:
                roll = o[0] - o[3]
                row += f"  {roll:>7.1f}"
            else:
                row += "  " + "       "
        print(row)

    # ----- Gap (ZM-1 minus Spcmic) per piece, per cutoff --------------------
    print()
    print("=" * 78)
    print("0 -> 3 rolloff GAP: ZM-1 minus Spcmic 3OA (per piece)")
    print("=" * 78)
    pairs = [("Franck",    "ZM-1 Franck",    "Spcmic 3OA Franck"),
             ("Prokofiev", "ZM-1 Prokofiev", "Spcmic 3OA Prok.")]
    print(f"{'Piece':<12}" + "".join(
        f"  {'full' if c is None else f'<{int(c)/1000:.0f} kHz':>7}" for c in CUTOFFS))
    print("-" * 78)
    for piece, kz, ks in pairs:
        row = f"{piece:<12}"
        for c in CUTOFFS:
            rz = results[kz][c][0] - results[kz][c][3]
            rs = results[ks][c][0] - results[ks][c][3]
            row += f"  {rz - rs:>7.1f}"
        print(row)

    print()
    print("Interpretation:")
    print(" - Full-band gap is the value reported in the paper (~19 dB Franck).")
    print(" - If the gap survives at <3 kHz, the headline finding is robust:")
    print(" - it reflects order-truncation, not high-frequency spatial aliasing.")


if __name__ == "__main__":
    main()
