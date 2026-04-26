#!/usr/bin/env python3
"""
analyze_paper.py
================

Single-source analysis for AES Copenhagen 2026 Submission 51:

    "Zylia ZM-1 vs. Harpex Spcmic: A Case Study of Higher-Order
     Ambisonic Recording Performance"

Reads HOA WAV recordings directly and writes:
  paper_results/per_file_metrics.csv     per-file rms / order energies / LUFS
  paper_results/spectral_band_diff.csv   ZM-1 minus Spcmic W-PSD per frequency
  paper_results/lufs_pairs.csv           LUFS deltas per (mic, piece)
  paper_results/spatial_energy.csv       per-order dBFS, rolloff, delta
  paper_results/directional.csv          X/Y/Z over W per file
  paper_results/paper_variables.tex      \\newcommand definitions for the paper

The manuscript imports paper_variables.tex via \\input{} so re-running this
script is the only step needed to keep all numeric claims in the paper
synchronized with the audio files.

LUFS-I is computed in-script via ITU-R BS.1770-5 K-weighting on the W channel
(no external dependency on pyloudnorm or REAPER render_stats).

Author: Bartlomiej Mroz
"""

import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import lfilter, welch
from scipy.ndimage import uniform_filter1d


# ---------------------------------------------------------------------------
# Recording inventory
# ---------------------------------------------------------------------------
DEFAULT_BASE = Path("/Volumes/PNY 1TB/HOA recordings by BM - all")
SESSION_AUG15 = "2024.08.15 -- ZM1 Spcmic Saramonic"
SESSION_APR30 = "2024.04.30 -- piano recording"

# (key, session, filename, mic, format, piece)
# `key` is also the suffix used in LaTeX command names.
RECORDINGS = [
    ("ZMOneFranck",        SESSION_AUG15, "3OA_ZM1_CFranck-PreludeChoralFugue.wav",     "ZM-1",   "3OA", "Franck"),
    ("ZMOneProkofiev",     SESSION_AUG15, "3OA_ZM1_SProkofiev-Sonata4.wav",             "ZM-1",   "3OA", "Prokofiev"),
    ("ZMOneGinastera",     SESSION_APR30, "3OA_ZM1_AGinastera-Sonata1.wav",             "ZM-1",   "3OA", "Ginastera"),
    ("SpcmicThreeOAFranck",    SESSION_AUG15, "3OA_Spcmic_CFranck-PreludeChoralFugue.wav", "Spcmic", "3OA", "Franck"),
    ("SpcmicThreeOAProkofiev", SESSION_AUG15, "3OA_Spcmic_SProkofiev-Sonata4.wav",         "Spcmic", "3OA", "Prokofiev"),
    ("SpcmicFiveOAFranck",     SESSION_AUG15, "5OA_Spcmic_CFranck-PreludeChoralFugue.wav", "Spcmic", "5OA", "Franck"),
    ("SpcmicFiveOAProkofiev",  SESSION_AUG15, "5OA_Spcmic_SProkofiev-Sonata4.wav",         "Spcmic", "5OA", "Prokofiev"),
    ("SpcmicFiveOAGinastera",  SESSION_APR30, "5OA_Spcmic_AGinastera-Sonata1.wav",         "Spcmic", "5OA", "Ginastera"),
]

# ACN ordering, channel ranges per Ambisonics order.
ORDER_RANGES = {0: (0, 1), 1: (1, 4), 2: (4, 9), 3: (9, 16), 4: (16, 25), 5: (25, 36)}

SPECTRAL_BAND_HZ = (200.0, 600.0)
SPECTRAL_REFERENCE_HZ = 1000.0

# Sub-aliasing cutoff for the spatial-energy robustness check. Pinardi
# et al. 2021 give the ZM-1 a 3rd-order usable bandwidth of 660-3080 Hz;
# above ~3 kHz the array is in spatial-aliasing territory by design.
SUB_ALIAS_CUTOFF_HZ = 3000.0


# ---------------------------------------------------------------------------
# Per-file streaming analysis
# ---------------------------------------------------------------------------
def stream_file(path, chunk_seconds=30):
    """Stream a multichannel WAV. Returns (sr, n_channels, n_frames,
    sum_of_squares_per_channel, full_W_signal)."""
    info = sf.info(path)
    sr = info.samplerate
    n_channels = info.channels
    n_frames = info.frames

    ssum = np.zeros(n_channels, dtype=np.float64)
    w_chunks = []
    chunk_size = sr * chunk_seconds

    with sf.SoundFile(path) as f:
        for block in f.blocks(blocksize=chunk_size, dtype="float32"):
            if block.ndim == 1:
                block = block.reshape(-1, 1)
            ssum += np.sum(block.astype(np.float64) ** 2, axis=0)
            w_chunks.append(block[:, 0].copy())

    return sr, n_channels, n_frames, ssum, np.concatenate(w_chunks)


def order_energies_dbfs(ssum, n_frames, n_channels, max_order):
    """Linear-mean per-channel RMS within each order, expressed in dBFS.
    Matches the methodology used to produce pub_fig09_spatial_energy.csv."""
    out = {}
    rms_per_channel = np.sqrt(ssum / n_frames)
    for order in range(max_order + 1):
        start, end = ORDER_RANGES[order]
        if end <= n_channels:
            avg_rms = float(np.mean(rms_per_channel[start:end]))
            out[order] = 20.0 * np.log10(avg_rms + 1e-20)
    return out


def order_energies_band_limited(audio_path, fmax_hz, max_order, nperseg=8192):
    """Same definition as order_energies_dbfs, but per-channel power is
    obtained by integrating the channel's Welch PSD over [0, fmax_hz].
    Used for the spatial-aliasing robustness check (~Pinardi 2021's
    sub-3 kHz 3OA usable band). Returns {order: dBFS}."""
    info = sf.info(audio_path)
    sr = info.samplerate
    n_channels = info.channels
    # Welch needs the full vector per channel; for a 19-min mono channel
    # at 48-96 kHz this is at most ~440 MB float32 -- manageable.
    data = sf.read(audio_path, dtype="float32", always_2d=True)[0]
    powers = np.zeros(n_channels)
    for ch in range(n_channels):
        freqs, pxx = welch(data[:, ch], fs=sr, nperseg=nperseg,
                           noverlap=nperseg // 2, window="hann")
        df = float(freqs[1] - freqs[0])
        mask = freqs <= fmax_hz
        powers[ch] = float(np.sum(pxx[mask]) * df)

    rms = np.sqrt(powers)
    out = {}
    for order in range(max_order + 1):
        start, end = ORDER_RANGES[order]
        if end <= n_channels:
            avg_rms = float(np.mean(rms[start:end]))
            out[order] = 20.0 * np.log10(avg_rms + 1e-20)
    return out


# ---------------------------------------------------------------------------
# ITU-R BS.1770-5 K-weighted integrated loudness on the W channel
# ---------------------------------------------------------------------------
def k_weighting_filters(sr):
    """Returns (b1, a1, b2, a2): pre-filter (high shelf) and RLB (high-pass).
    Coefficients per BS.1770-5 (sample-rate-aware via bilinear transform of
    the analog prototype)."""
    # Pre-filter: high-shelf at ~1681 Hz, +4 dB
    f0 = 1681.974450955533
    G = 3.999843853973347
    Q = 0.7071752369554196
    K = np.tan(np.pi * f0 / sr)
    Vh = 10 ** (G / 20.0)
    Vb = Vh ** 0.4996667741545416
    a0_ = 1.0 + K / Q + K * K
    b1 = np.array([
        (Vh + Vb * K / Q + K * K) / a0_,
        2.0 * (K * K - Vh) / a0_,
        (Vh - Vb * K / Q + K * K) / a0_,
    ])
    a1 = np.array([
        1.0,
        2.0 * (K * K - 1.0) / a0_,
        (1.0 - K / Q + K * K) / a0_,
    ])
    # RLB filter: high-pass at ~38.13 Hz
    f0 = 38.13547087602444
    Q = 0.5003270373238773
    K = np.tan(np.pi * f0 / sr)
    a0_ = 1.0 + K / Q + K * K
    b2 = np.array([1.0, -2.0, 1.0]) / a0_
    a2 = np.array([
        1.0,
        2.0 * (K * K - 1.0) / a0_,
        (1.0 - K / Q + K * K) / a0_,
    ])
    return b1, a1, b2, a2


def lufs_integrated_w(w, sr):
    """ITU-R BS.1770-5 integrated loudness on the W channel (treated as
    mono). Implements K-weighting + 400 ms blocks (75% overlap) + absolute
    -70 LUFS gate + relative -10 dB gate."""
    b1, a1, b2, a2 = k_weighting_filters(sr)
    y = lfilter(b1, a1, w)
    y = lfilter(b2, a2, y)

    block = int(round(0.400 * sr))
    hop = int(round(0.100 * sr))  # 75% overlap of 400 ms blocks
    n = len(y)
    if n < block:
        return float("nan")

    n_blocks = 1 + (n - block) // hop
    means = np.empty(n_blocks)
    for i in range(n_blocks):
        s = i * hop
        chunk = y[s:s + block]
        means[i] = np.mean(chunk * chunk)

    # Loudness per block (mono channel weight 1.0)
    with np.errstate(divide="ignore"):
        block_lufs = -0.691 + 10.0 * np.log10(means + 1e-30)

    # Absolute gate at -70 LUFS
    abs_mask = block_lufs >= -70.0
    if not np.any(abs_mask):
        return float("nan")
    abs_mean = np.mean(means[abs_mask])
    abs_lufs = -0.691 + 10.0 * np.log10(abs_mean + 1e-30)

    # Relative gate at abs - 10 dB
    rel_thr = abs_lufs - 10.0
    rel_mask = abs_mask & (block_lufs >= rel_thr)
    if not np.any(rel_mask):
        return float("nan")
    rel_mean = np.mean(means[rel_mask])
    return float(-0.691 + 10.0 * np.log10(rel_mean + 1e-30))


# ---------------------------------------------------------------------------
# REAPER render_stats.html parsing (multichannel BS.1770 from REAPER)
# ---------------------------------------------------------------------------
def lufs_from_reaper_html(wav_path):
    """Read REAPER's integrated LUFS for `wav_path` from its companion
    .render_stats.html file (multichannel BS.1770, summing all channels).
    Returns (lufs_i, true_peak_db, lra) with None entries if missing."""
    html = wav_path.with_suffix(".render_stats.html")
    if not html.exists():
        return None, None, None
    text = html.read_text(encoding="utf-8", errors="replace")

    lufs = tp = lra = None

    # Modern REAPER renders an HTML table with LUFS-I column.
    m = re.search(r"<th>[^<]*LUFS-I[^<]*</th>", text, re.IGNORECASE)
    if m:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.IGNORECASE | re.DOTALL)
        for row in rows:
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row,
                               re.IGNORECASE | re.DOTALL)
            cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            if not cells or any("LUFS-I" in c for c in cells):
                continue
            for cell in cells:
                try:
                    v = float(cell)
                    if -60.0 <= v <= 0.0:
                        lufs = v
                        break
                except ValueError:
                    continue
            if lufs is not None:
                break

    # Older REAPER versions expose a JS-style payload instead.
    if lufs is None:
        m = re.search(r"integrated:\s*\['LUFS-I'\s*,\s*[\d.]+\s*,\s*'([-\d.]+)'\s*\]", text)
        if m:
            lufs = float(m.group(1))
    m = re.search(r"truepeak:\s*\['True Peak'\s*,\s*'([-\d.]+)'\s*\]", text)
    if m:
        tp = float(m.group(1))
    m = re.search(r"dynrange:\s*\['LRA'\s*,\s*\[[\d.]+\s*,\s*'([-\d.]+)'\]\s*,\s*\[[\d.]+\s*,\s*'([-\d.]+)'\]\s*\]", text)
    if m:
        lra = float(m.group(2)) - float(m.group(1))
    return lufs, tp, lra


# ---------------------------------------------------------------------------
# Spectral analysis
# ---------------------------------------------------------------------------
def w_psd_db(w, sr, nperseg=8192):
    """Welch PSD of the W channel, returned as (freqs, dB)."""
    f, p = welch(w, fs=sr, nperseg=nperseg, noverlap=nperseg // 2, window="hann")
    return f, 10.0 * np.log10(p + 1e-20)


def smooth_octave(freqs, db, fraction=6):
    """1/N-octave smoothing of a magnitude curve in dB."""
    log_f = np.log2(freqs[1:] + 1.0)
    spacing = np.mean(np.diff(log_f))
    win = max(1, int(round(1.0 / (fraction * spacing))))
    out = db.copy()
    out[1:] = uniform_filter1d(out[1:], win)
    return out


def reference_normalize(freqs, db, ref_hz=SPECTRAL_REFERENCE_HZ):
    """Subtract the value of `db` at `ref_hz` so that ref_hz reads 0 dB."""
    idx = int(np.argmin(np.abs(freqs - ref_hz)))
    return db - db[idx]


# ---------------------------------------------------------------------------
# Main analysis driver
# ---------------------------------------------------------------------------
def run_analysis(base_dir, force=False):
    metrics = {}
    print(f"[i] Analysing {len(RECORDINGS)} recordings in {base_dir}")

    for key, session, fname, mic, fmt, piece in RECORDINGS:
        path = base_dir / session / "render" / fname
        if not path.exists():
            print(f"[!] Missing: {path}")
            metrics[key] = None
            continue

        print(f"  - {key} ({mic} {fmt}, {piece})")
        sr, n_channels, n_frames, ssum, w = stream_file(path)
        max_order = 5 if n_channels >= 36 else 3 if n_channels >= 16 else 1 if n_channels >= 4 else 0

        rec = {
            "mic": mic, "format": fmt, "piece": piece,
            "session": session, "file": fname,
            "sr": sr, "n_channels": n_channels, "n_frames": n_frames,
            "duration_s": n_frames / sr,
            "max_order": max_order,
        }

        # Per-channel RMS
        rms = np.sqrt(ssum / n_frames)
        rec["W_rms"] = float(rms[0])
        if n_channels >= 4:
            # ACN: 0=W, 1=Y, 2=Z, 3=X
            rec["Y_rms"] = float(rms[1])
            rec["Z_rms"] = float(rms[2])
            rec["X_rms"] = float(rms[3])
            rec["X_over_W"] = float(rms[3] / rms[0])
            rec["Y_over_W"] = float(rms[1] / rms[0])
            rec["Z_over_W"] = float(rms[2] / rms[0])

        # Energy per order in dBFS
        rec["order_dbfs"] = order_energies_dbfs(ssum, n_frames, n_channels, max_order)
        if 0 in rec["order_dbfs"] and 3 in rec["order_dbfs"]:
            rec["rolloff_0_to_3_dB"] = float(rec["order_dbfs"][0] - rec["order_dbfs"][3])

        # Sub-aliasing-band check: only run for the 3OA pieces actually
        # cited in the rolloff comparison (Aug 15 session). It re-reads
        # the file via Welch, so skip it for the bigger 5OA Spcmic files
        # and the Ginastera session.
        if mic in ("ZM-1", "Spcmic") and fmt == "3OA" and piece in ("Franck", "Prokofiev"):
            print(f"     ... sub-aliasing check (<{int(SUB_ALIAS_CUTOFF_HZ)} Hz)")
            sub = order_energies_band_limited(path, SUB_ALIAS_CUTOFF_HZ, max_order)
            rec["order_dbfs_sub_alias"] = sub
            if 0 in sub and 3 in sub:
                rec["rolloff_0_to_3_dB_sub_alias"] = float(sub[0] - sub[3])

        # LUFS-I on W via in-script BS.1770-5 K-weighting (W-only reference)
        rec["lufs_i_W"] = lufs_integrated_w(w, sr)

        # LUFS-I from REAPER's render_stats.html (multichannel BS.1770).
        # This matches what the paper cites; it sums energy across all
        # rendered Ambisonics channels per REAPER's loudness implementation.
        lufs_mc, tp, lra = lufs_from_reaper_html(path)
        rec["lufs_i_multichannel"] = lufs_mc
        rec["true_peak_db"] = tp
        rec["lra"] = lra

        # Smoothed W-PSD normalized to 0 dB at 1 kHz
        f, db = w_psd_db(w, sr)
        db = smooth_octave(f, db, fraction=6)
        db = reference_normalize(f, db)
        rec["_freqs"] = f
        rec["_w_psd_db_norm"] = db

        metrics[key] = rec

    return metrics


# ---------------------------------------------------------------------------
# Derived metrics & writers
# ---------------------------------------------------------------------------
def derive_pair_metrics(m):
    """Cross-file derived numbers that go into the paper."""
    d = {}

    # ---- Spectral elevation in 200--600 Hz: ZM-1 vs Spcmic 3OA (Franck) ----
    keys = [
        ("Franck",    "ZMOneFranck",    "SpcmicThreeOAFranck"),
        ("Prokofiev", "ZMOneProkofiev", "SpcmicThreeOAProkofiev"),
    ]
    band_diffs = []
    band_freqs = None
    for piece, kz, ks in keys:
        if m.get(kz) is None or m.get(ks) is None:
            continue
        f = m[kz]["_freqs"]
        diff = m[kz]["_w_psd_db_norm"] - m[ks]["_w_psd_db_norm"]
        mask = (f >= SPECTRAL_BAND_HZ[0]) & (f <= SPECTRAL_BAND_HZ[1])
        band_diffs.append((piece, f[mask], diff[mask]))
        band_freqs = f[mask]

    if band_diffs:
        all_diff = np.concatenate([d_ for _, _, d_ in band_diffs])
        d["spectral_band_min_db"] = float(np.min(all_diff))
        d["spectral_band_max_db"] = float(np.max(all_diff))
        d["spectral_band_mean_db"] = float(np.mean(all_diff))
        d["_spectral_band_curves"] = band_diffs  # for CSV dump
        for piece, freqs, diff in band_diffs:
            d[f"spectral_band_min_{piece}"] = float(np.min(diff))
            d[f"spectral_band_max_{piece}"] = float(np.max(diff))
            d[f"spectral_band_mean_{piece}"] = float(np.mean(diff))

    # ---- LUFS deltas: Spcmic minus ZM-1 (positive => Spcmic louder) ----
    pairs = [
        ("Franck_3OA",    "ZMOneFranck",    "SpcmicThreeOAFranck"),
        ("Prokofiev_3OA", "ZMOneProkofiev", "SpcmicThreeOAProkofiev"),
        ("Ginastera_5OA", "ZMOneGinastera", "SpcmicFiveOAGinastera"),
        # also report 5OA pairs for August 15 for completeness
        ("Franck_5OA",    "ZMOneFranck",    "SpcmicFiveOAFranck"),
        ("Prokofiev_5OA", "ZMOneProkofiev", "SpcmicFiveOAProkofiev"),
    ]
    deltas_mc = []     # multichannel deltas (paper's primary claim)
    deltas_w  = []     # W-only deltas (reproducible from WAV alone)
    pair_rows = []
    for label, kz, ks in pairs:
        if m.get(kz) is None or m.get(ks) is None:
            continue
        zlu_mc = m[kz].get("lufs_i_multichannel")
        slu_mc = m[ks].get("lufs_i_multichannel")
        zlu_w  = m[kz].get("lufs_i_W")
        slu_w  = m[ks].get("lufs_i_W")
        delta_mc = (slu_mc - zlu_mc) if (zlu_mc is not None and slu_mc is not None) else None
        delta_w  = (slu_w  - zlu_w)  if (zlu_w  is not None and slu_w  is not None
                                          and np.isfinite(zlu_w) and np.isfinite(slu_w)) else None
        if delta_mc is not None:
            deltas_mc.append((label, delta_mc))
        if delta_w is not None:
            deltas_w.append((label, delta_w))
        pair_rows.append({
            "pair": label, "zm1_key": kz, "spcmic_key": ks,
            "lufs_zm1_multichannel": zlu_mc, "lufs_spcmic_multichannel": slu_mc,
            "delta_multichannel_dB": delta_mc,
            "lufs_zm1_W": zlu_w, "lufs_spcmic_W": slu_w,
            "delta_W_dB": delta_w,
        })
    d["_lufs_pairs"] = pair_rows
    # Range over the three pairs the paper actually reports (3OA Franck, 3OA
    # Prokofiev, 5OA Ginastera -- 5OA used because no 3OA Spcmic was rendered
    # for the April 30 session).
    paper_labels = ("Franck_3OA", "Prokofiev_3OA", "Ginastera_5OA")
    primary_mc = [v for lbl, v in deltas_mc if lbl in paper_labels]
    if primary_mc:
        d["lufs_delta_mc_min"] = float(min(primary_mc))
        d["lufs_delta_mc_max"] = float(max(primary_mc))
    primary_w = [v for lbl, v in deltas_w if lbl in paper_labels]
    if primary_w:
        d["lufs_delta_w_min"] = float(min(primary_w))
        d["lufs_delta_w_max"] = float(max(primary_w))

    # ---- Spatial energy rolloff (0 -> 3) ----
    # Average across pieces analysed (Aug 15 session: Franck + Prokofiev)
    def avg_rolloff(keys):
        vals = [m[k]["rolloff_0_to_3_dB"] for k in keys
                if m.get(k) is not None and "rolloff_0_to_3_dB" in m[k]]
        return float(np.mean(vals)) if vals else None

    d["zm1_rolloff_0_3"] = avg_rolloff(["ZMOneFranck", "ZMOneProkofiev"])
    d["spcmic3oa_rolloff_0_3"] = avg_rolloff(["SpcmicThreeOAFranck", "SpcmicThreeOAProkofiev"])
    d["spcmic5oa_rolloff_0_3"] = avg_rolloff(["SpcmicFiveOAFranck", "SpcmicFiveOAProkofiev"])
    if d["zm1_rolloff_0_3"] and d["spcmic3oa_rolloff_0_3"]:
        d["rolloff_delta_mean"] = d["zm1_rolloff_0_3"] - d["spcmic3oa_rolloff_0_3"]
    # Per-piece rolloff deltas (ZM-1 minus Spcmic 3OA, same piece)
    for piece, kz, ks in [
        ("Franck",    "ZMOneFranck",    "SpcmicThreeOAFranck"),
        ("Prokofiev", "ZMOneProkofiev", "SpcmicThreeOAProkofiev"),
    ]:
        if m.get(kz) and m.get(ks):
            r1 = m[kz].get("rolloff_0_to_3_dB")
            r2 = m[ks].get("rolloff_0_to_3_dB")
            if r1 is not None and r2 is not None:
                d[f"rolloff_delta_{piece}"] = r1 - r2
            # Same delta but band-limited to the sub-aliasing region
            r1s = m[kz].get("rolloff_0_to_3_dB_sub_alias")
            r2s = m[ks].get("rolloff_0_to_3_dB_sub_alias")
            if r1s is not None and r2s is not None:
                d[f"rolloff_delta_sub_alias_{piece}"] = r1s - r2s

    # ---- Directional X/Y/Z over W: ranges per microphone family ----
    # Paper's directional claim collapses both pieces. Report X separately
    # (the dominant component, per the AoA paper) and the full (X,Y,Z) range.
    def collect(keys, comp):
        vals = [m[k][f"{comp}_over_W"] for k in keys if m.get(k) is not None]
        return vals

    zm1_keys = ["ZMOneFranck", "ZMOneProkofiev"]
    sp3_keys = ["SpcmicThreeOAFranck", "SpcmicThreeOAProkofiev"]

    for label, keys in [("zm1", zm1_keys), ("spcmic3oa", sp3_keys)]:
        x = collect(keys, "X")
        y = collect(keys, "Y")
        z = collect(keys, "Z")
        if x:
            d[f"{label}_X_min"] = float(min(x)); d[f"{label}_X_max"] = float(max(x))
        if y:
            d[f"{label}_Y_min"] = float(min(y)); d[f"{label}_Y_max"] = float(max(y))
        if z:
            d[f"{label}_Z_min"] = float(min(z)); d[f"{label}_Z_max"] = float(max(z))
        all_xyz = x + y + z
        if all_xyz:
            d[f"{label}_xyz_min"] = float(min(all_xyz))
            d[f"{label}_xyz_max"] = float(max(all_xyz))

    # ---- Total durations ----
    def total(keys):
        s = sum(m[k]["duration_s"] for k in keys if m.get(k) is not None)
        return s / 60.0
    d["aug15_total_minutes"] = total(["ZMOneFranck", "ZMOneProkofiev"])
    d["apr30_total_minutes"] = total(["ZMOneGinastera"])

    return d


def write_per_file_csv(metrics, out_path):
    fieldnames = [
        "key", "mic", "format", "piece", "session", "file",
        "sr", "n_channels", "duration_s",
        "W_rms", "X_rms", "Y_rms", "Z_rms",
        "X_over_W", "Y_over_W", "Z_over_W",
        "lufs_i_multichannel", "lufs_i_W",
        "true_peak_db", "lra",
        "order0_dBFS", "order1_dBFS", "order2_dBFS",
        "order3_dBFS", "order4_dBFS", "order5_dBFS",
        "rolloff_0_to_3_dB",
    ]
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for key, rec in metrics.items():
            if rec is None:
                continue
            row = {
                "key": key,
                "mic": rec["mic"], "format": rec["format"], "piece": rec["piece"],
                "session": rec["session"], "file": rec["file"],
                "sr": rec["sr"], "n_channels": rec["n_channels"],
                "duration_s": f"{rec['duration_s']:.3f}",
                "W_rms": rec.get("W_rms", ""),
                "X_rms": rec.get("X_rms", ""), "Y_rms": rec.get("Y_rms", ""),
                "Z_rms": rec.get("Z_rms", ""),
                "X_over_W": rec.get("X_over_W", ""),
                "Y_over_W": rec.get("Y_over_W", ""),
                "Z_over_W": rec.get("Z_over_W", ""),
                "lufs_i_multichannel": rec.get("lufs_i_multichannel", ""),
                "lufs_i_W": rec.get("lufs_i_W", ""),
                "true_peak_db": rec.get("true_peak_db", ""),
                "lra": rec.get("lra", ""),
                "rolloff_0_to_3_dB": rec.get("rolloff_0_to_3_dB", ""),
            }
            for o in range(6):
                row[f"order{o}_dBFS"] = rec["order_dbfs"].get(o, "")
            w.writerow(row)


def write_spectral_csv(derived, out_path):
    rows = []
    for piece, freqs, diff in derived.get("_spectral_band_curves", []):
        for fr, dv in zip(freqs, diff):
            rows.append({"piece": piece, "freq_hz": float(fr),
                         "zm1_minus_spcmic_dB": float(dv)})
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["piece", "freq_hz", "zm1_minus_spcmic_dB"])
        w.writeheader()
        w.writerows(rows)


def write_lufs_csv(derived, out_path):
    rows = derived.get("_lufs_pairs", [])
    fieldnames = [
        "pair", "zm1_key", "spcmic_key",
        "lufs_zm1_multichannel", "lufs_spcmic_multichannel", "delta_multichannel_dB",
        "lufs_zm1_W", "lufs_spcmic_W", "delta_W_dB",
    ]
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            row = {}
            for k in fieldnames:
                v = r.get(k)
                row[k] = f"{v:.3f}" if isinstance(v, float) else (v if v is not None else "")
            w.writerow(row)


def write_spatial_csv(metrics, out_path):
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "key", "mic", "format", "piece",
            "order0_dBFS", "order1_dBFS", "order2_dBFS",
            "order3_dBFS", "order4_dBFS", "order5_dBFS",
            "rolloff_0_to_3_dB",
        ])
        w.writeheader()
        for key, rec in metrics.items():
            if rec is None:
                continue
            row = {"key": key, "mic": rec["mic"], "format": rec["format"], "piece": rec["piece"]}
            for o in range(6):
                v = rec["order_dbfs"].get(o, "")
                row[f"order{o}_dBFS"] = f"{v:.3f}" if isinstance(v, float) else v
            v = rec.get("rolloff_0_to_3_dB", "")
            row["rolloff_0_to_3_dB"] = f"{v:.3f}" if isinstance(v, float) else v
            w.writerow(row)


def write_directional_csv(metrics, out_path):
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "key", "mic", "format", "piece",
            "W_rms", "X_rms", "Y_rms", "Z_rms",
            "X_over_W", "Y_over_W", "Z_over_W",
        ])
        w.writeheader()
        for key, rec in metrics.items():
            if rec is None or "X_over_W" not in rec:
                continue
            row = {"key": key, "mic": rec["mic"], "format": rec["format"], "piece": rec["piece"]}
            for k in ["W_rms", "X_rms", "Y_rms", "Z_rms",
                      "X_over_W", "Y_over_W", "Z_over_W"]:
                row[k] = f"{rec[k]:.6f}"
            w.writerow(row)


# ---------------------------------------------------------------------------
# LaTeX writer
# ---------------------------------------------------------------------------
def fmt(v, decimals=2):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "??"
    return f"{v:.{decimals}f}"


def write_tex(metrics, derived, out_path, base_dir):
    lines = []
    lines.append("% Auto-generated by analyze_paper.py - do not edit by hand.")
    lines.append(f"% Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"% Source recordings: {base_dir}")
    lines.append("%")
    lines.append("% Two LUFS-I values are emitted per file:")
    lines.append("%   * \\LUFSMC<key>  - multichannel BS.1770 from REAPER's render_stats.html")
    lines.append("%                     (sums energy across all rendered channels; this is")
    lines.append("%                     the value the paper currently cites).")
    lines.append("%   * \\LUFSW<key>   - W-channel only, computed in-script via BS.1770-5")
    lines.append("%                     K-weighting on the omnidirectional component alone.")
    lines.append("% Range commands: \\LUFSDeltaMCMin/Max and \\LUFSDeltaWMin/Max.")
    lines.append("")

    def newcmd(name, value):
        lines.append(f"\\newcommand{{\\{name}}}{{{value}}}")

    # --- Durations -----------------------------------------------------------
    lines.append("% --- Durations (computed from WAV) ---")
    newcmd("AugFifteenDurMin", fmt(derived.get("aug15_total_minutes"), 1))
    newcmd("AprThirtyDurMin",  fmt(derived.get("apr30_total_minutes"), 1))
    for key in ("ZMOneFranck", "ZMOneProkofiev", "ZMOneGinastera"):
        rec = metrics.get(key)
        if rec is not None:
            newcmd(f"DurMin{key}", fmt(rec["duration_s"] / 60.0, 1))
    lines.append("")

    # --- Spectral elevation 200-600 Hz --------------------------------------
    lines.append("% --- W-channel spectral elevation, ZM-1 minus Spcmic, "
                 f"{int(SPECTRAL_BAND_HZ[0])}-{int(SPECTRAL_BAND_HZ[1])} Hz ---")
    newcmd("SpectralBandLow",  f"{int(SPECTRAL_BAND_HZ[0])}")
    newcmd("SpectralBandHigh", f"{int(SPECTRAL_BAND_HZ[1])}")
    newcmd("SpectralEleMin",  fmt(derived.get("spectral_band_min_db"), 1))
    newcmd("SpectralEleMax",  fmt(derived.get("spectral_band_max_db"), 1))
    newcmd("SpectralEleMean", fmt(derived.get("spectral_band_mean_db"), 1))
    for piece in ("Franck", "Prokofiev"):
        for stat, key in (("Min", "min"), ("Max", "max"), ("Mean", "mean")):
            v = derived.get(f"spectral_band_{key}_{piece}")
            if v is not None:
                newcmd(f"SpectralEle{stat}{piece}", fmt(v, 1))
    lines.append("")

    # --- LUFS-I -------------------------------------------------------------
    lines.append("% --- LUFS-I per file (multichannel REAPER + W-channel BS.1770-5) ---")
    for key, rec in metrics.items():
        if rec is None:
            continue
        v_mc = rec.get("lufs_i_multichannel")
        v_w  = rec.get("lufs_i_W")
        if v_mc is not None:
            newcmd(f"LUFSMC{key}", fmt(v_mc, 2))
        if v_w is not None and np.isfinite(v_w):
            newcmd(f"LUFSW{key}", fmt(v_w, 2))
    if derived.get("lufs_delta_mc_min") is not None:
        newcmd("LUFSDeltaMCMin", fmt(derived["lufs_delta_mc_min"], 1))
        newcmd("LUFSDeltaMCMax", fmt(derived["lufs_delta_mc_max"], 1))
    if derived.get("lufs_delta_w_min") is not None:
        newcmd("LUFSDeltaWMin", fmt(derived["lufs_delta_w_min"], 1))
        newcmd("LUFSDeltaWMax", fmt(derived["lufs_delta_w_max"], 1))
        # Inverted-sign companions: useful when the prose describes the
        # reversed direction (ZM-1 is louder than Spcmic on the W channel).
        # Renders as e.g. "0.8--2.6 dB" instead of "(-2.6)-(-0.8) dB".
        newcmd("LUFSDeltaWInvMin", fmt(-derived["lufs_delta_w_max"], 1))
        newcmd("LUFSDeltaWInvMax", fmt(-derived["lufs_delta_w_min"], 1))
    lines.append("")

    # --- Spatial energy per order ------------------------------------------
    lines.append("% --- Spatial energy per Ambisonics order (dBFS, RMS-mean) ---")
    for key, rec in metrics.items():
        if rec is None:
            continue
        for o, v in rec["order_dbfs"].items():
            digit = ["Zero","One","Two","Three","Four","Five"][o]
            newcmd(f"Order{digit}{key}", fmt(v, 1))
        if "rolloff_0_to_3_dB" in rec:
            newcmd(f"Rolloff{key}", fmt(rec["rolloff_0_to_3_dB"], 1))

    if derived.get("zm1_rolloff_0_3") is not None:
        newcmd("ZMOneRolloffMean",      fmt(derived["zm1_rolloff_0_3"], 1))
    if derived.get("spcmic3oa_rolloff_0_3") is not None:
        newcmd("SpcmicThreeOARolloffMean", fmt(derived["spcmic3oa_rolloff_0_3"], 1))
    if derived.get("spcmic5oa_rolloff_0_3") is not None:
        newcmd("SpcmicFiveOARolloffMean",  fmt(derived["spcmic5oa_rolloff_0_3"], 1))
    if derived.get("rolloff_delta_mean") is not None:
        newcmd("RolloffDeltaMean", fmt(derived["rolloff_delta_mean"], 1))
    if derived.get("rolloff_delta_Franck") is not None:
        newcmd("RolloffDeltaFranck", fmt(derived["rolloff_delta_Franck"], 1))
    if derived.get("rolloff_delta_Prokofiev") is not None:
        newcmd("RolloffDeltaProkofiev", fmt(derived["rolloff_delta_Prokofiev"], 1))

    # Sub-aliasing-band rolloff (Pinardi-style ZM-1 3OA usable band <3 kHz)
    newcmd("SubAliasCutoffHz", f"{int(SUB_ALIAS_CUTOFF_HZ)}")
    for key, rec in metrics.items():
        if rec is None or "rolloff_0_to_3_dB_sub_alias" not in rec:
            continue
        newcmd(f"Rolloff{key}SubAlias",
               fmt(rec["rolloff_0_to_3_dB_sub_alias"], 1))
    if derived.get("rolloff_delta_sub_alias_Franck") is not None:
        newcmd("RolloffDeltaSubAliasFranck",
               fmt(derived["rolloff_delta_sub_alias_Franck"], 1))
        # Plain alias (paper text uses \RolloffDeltaSubAlias for the
        # headline number; we point it at the Franck value to mirror
        # \RolloffDeltaFranck above).
        newcmd("RolloffDeltaSubAlias",
               fmt(derived["rolloff_delta_sub_alias_Franck"], 1))
    if derived.get("rolloff_delta_sub_alias_Prokofiev") is not None:
        newcmd("RolloffDeltaSubAliasProkofiev",
               fmt(derived["rolloff_delta_sub_alias_Prokofiev"], 1))
    lines.append("")

    # --- Directional X/Y/Z over W ------------------------------------------
    lines.append("% --- Directional first-order ratios (RMS / W RMS) ---")
    for key, rec in metrics.items():
        if rec is None or "X_over_W" not in rec:
            continue
        for comp in ("X", "Y", "Z"):
            newcmd(f"Dir{comp}{key}", fmt(rec[f"{comp}_over_W"], 2))

    # Per-mic ranges (across both pieces)
    for label, prefix in [("ZMOne", "zm1"), ("SpcmicThreeOA", "spcmic3oa")]:
        for comp in ("X", "Y", "Z"):
            mn = derived.get(f"{prefix}_{comp}_min")
            mx = derived.get(f"{prefix}_{comp}_max")
            if mn is not None:
                newcmd(f"Dir{comp}{label}Min", fmt(mn, 2))
                newcmd(f"Dir{comp}{label}Max", fmt(mx, 2))
        # combined X,Y,Z range
        mn = derived.get(f"{prefix}_xyz_min")
        mx = derived.get(f"{prefix}_xyz_max")
        if mn is not None:
            newcmd(f"DirXYZ{label}Min", fmt(mn, 2))
            newcmd(f"DirXYZ{label}Max", fmt(mx, 2))
    lines.append("")

    out_path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", type=Path, default=DEFAULT_BASE,
                    help=f"Base directory holding session folders (default: {DEFAULT_BASE})")
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parent / "paper_results",
                    help="Output directory for CSV/TEX")
    args = ap.parse_args()

    if not args.base.exists():
        print(f"[!] Base directory not found: {args.base}", file=sys.stderr)
        sys.exit(1)
    args.out.mkdir(parents=True, exist_ok=True)

    metrics = run_analysis(args.base)
    derived = derive_pair_metrics(metrics)

    write_per_file_csv(metrics, args.out / "per_file_metrics.csv")
    write_spectral_csv(derived, args.out / "spectral_band_diff.csv")
    write_lufs_csv(derived, args.out / "lufs_pairs.csv")
    write_spatial_csv(metrics, args.out / "spatial_energy.csv")
    write_directional_csv(metrics, args.out / "directional.csv")
    write_tex(metrics, derived, args.out / "paper_variables.tex", args.base)

    print()
    print(f"[OK] Wrote {args.out}/")
    for p in sorted(args.out.iterdir()):
        print(f"     {p.name}")


if __name__ == "__main__":
    main()
