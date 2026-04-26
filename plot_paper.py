#!/usr/bin/env python3
"""
plot_paper.py
=============

Companion to analyze_paper.py: regenerates the figures for AES Copenhagen
2026 Submission 51 directly from the source WAV files. Each figure is
written to paper_results/ as both PNG (for editor preview) and PDF (for
LaTeX inclusion).

Figures produced:
  fig_spatial_energy.{png,pdf}   per-order RMS, ZM-1 vs Spcmic (3OA, 5OA)
  fig_spectral.{png,pdf}         W-channel PSD, normalized at 1 kHz
  fig_lufs.{png,pdf}             LUFS-I (multichannel) bar chart per piece
  fig_directional.{png,pdf}      first-order X/Y/Z over W per microphone

Usage:
    python plot_paper.py
    python plot_paper.py --base-dir /path/to/hoa-corpus

Author: Bartlomiej Mroz
"""

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import soundfile as sf
from scipy.signal import welch
from scipy.ndimage import uniform_filter1d

# Reuse the analysis utilities from analyze_paper.py
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_paper import (  # noqa: E402
    DEFAULT_BASE, RECORDINGS, ORDER_RANGES,
    SPECTRAL_BAND_HZ, SPECTRAL_REFERENCE_HZ,
    stream_file, order_energies_dbfs,
    lufs_from_reaper_html, w_psd_db, smooth_octave, reference_normalize,
)


COLOR_ZM = "#1f77b4"
COLOR_SP3 = "#ff7f0e"
COLOR_SP5 = "#2ca02c"


# ---------------------------------------------------------------------------
def figure_spatial_energy(metrics, out_path):
    """Per-order RMS (dBFS) for ZM-1 (3OA), Spcmic 3OA, Spcmic 5OA."""
    fig, ax = plt.subplots(figsize=(6.0, 3.6))
    series = [
        ("ZM-1 (3OA)",  ["ZMOneFranck", "ZMOneProkofiev"],         COLOR_ZM,  "o"),
        ("Spcmic (3OA)", ["SpcmicThreeOAFranck", "SpcmicThreeOAProkofiev"], COLOR_SP3, "s"),
        ("Spcmic (5OA)", ["SpcmicFiveOAFranck", "SpcmicFiveOAProkofiev"],   COLOR_SP5, "^"),
    ]
    for label, keys, color, marker in series:
        # Average per-order dBFS across both pieces (Aug 15 session).
        recs = [metrics[k] for k in keys if metrics.get(k) is not None]
        if not recs:
            continue
        orders = sorted(recs[0]["order_dbfs"].keys())
        vals = [np.mean([r["order_dbfs"][o] for r in recs]) for o in orders]
        ax.plot(orders, vals, marker=marker, markersize=8, linewidth=2.0,
                linestyle="--", color=color, label=label, alpha=0.9)

    ax.set_xlabel("Ambisonics order")
    ax.set_ylabel("RMS level (dBFS)")
    ax.grid(True, alpha=0.3, linestyle=":")
    ax.legend(loc="upper right", fontsize=9)
    ax.set_xticks(range(0, 6))
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(out_path.with_suffix(f".{ext}"), dpi=300, bbox_inches="tight")
    plt.close(fig)


def figure_spectral(metrics, out_path):
    """W-channel PSD comparison (smoothed, normalized at 1 kHz)."""
    fig, ax = plt.subplots(figsize=(6.0, 3.6))
    plot_specs = [
        ("ZM-1 (3OA)",   "ZMOneFranck",         COLOR_ZM,  "-"),
        ("Spcmic (3OA)", "SpcmicThreeOAFranck", COLOR_SP3, "-"),
        ("Spcmic (5OA)", "SpcmicFiveOAFranck",  COLOR_SP5, "--"),
    ]
    # Track data extents so the y-axis can fit every curve.
    plotted_min = []
    plotted_max = []
    for label, key, color, ls in plot_specs:
        rec = metrics.get(key)
        if rec is None:
            continue
        f = rec["_freqs"]; db = rec["_w_psd_db_norm"]
        m = (f >= 20) & (f <= 20000)
        ax.semilogx(f[m], db[m], linestyle=ls, color=color, linewidth=1.6,
                    alpha=0.9, label=label)
        plotted_min.append(float(np.min(db[m])))
        plotted_max.append(float(np.max(db[m])))

    # Highlight the 200-600 Hz analysis band
    ax.axvspan(SPECTRAL_BAND_HZ[0], SPECTRAL_BAND_HZ[1],
               color="#d62728", alpha=0.10,
               label=f"{int(SPECTRAL_BAND_HZ[0])}-{int(SPECTRAL_BAND_HZ[1])} Hz band")
    ax.axvline(SPECTRAL_REFERENCE_HZ, color="gray", linestyle=":",
               linewidth=0.8, alpha=0.6)
    ax.set_xlim(20, 20000)
    if plotted_min and plotted_max:
        # Cap floor at -40 dB; below that the curves are essentially noise
        # for piano content (no useful detail past 8-10 kHz).
        hi = 5 * int(np.ceil((max(plotted_max) + 3) / 5))
        ax.set_ylim(-40, hi)
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Relative level (dB, normalized at 1 kHz)")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(loc="lower left", fontsize=9)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(out_path.with_suffix(f".{ext}"), dpi=300, bbox_inches="tight")
    plt.close(fig)


def figure_lufs(metrics, out_path):
    """LUFS-I bar chart per microphone and piece (multichannel, REAPER)."""
    pieces = ["Franck", "Prokofiev", "Ginastera"]
    mic_keys = [
        ("ZM-1 (3OA)",    {"Franck": "ZMOneFranck", "Prokofiev": "ZMOneProkofiev",
                            "Ginastera": "ZMOneGinastera"}, COLOR_ZM),
        ("Spcmic (3OA)",  {"Franck": "SpcmicThreeOAFranck",
                            "Prokofiev": "SpcmicThreeOAProkofiev"},                COLOR_SP3),
        ("Spcmic (5OA)",  {"Franck": "SpcmicFiveOAFranck",
                            "Prokofiev": "SpcmicFiveOAProkofiev",
                            "Ginastera": "SpcmicFiveOAGinastera"},                  COLOR_SP5),
    ]

    fig, ax = plt.subplots(figsize=(6.0, 3.6))
    x = np.arange(len(pieces))
    width = 0.27
    for i, (label, keys, color) in enumerate(mic_keys):
        vals = []
        for p in pieces:
            k = keys.get(p)
            v = metrics.get(k, {}).get("lufs_i_multichannel") if k else None
            vals.append(v if v is not None else np.nan)
        offset = (i - 1) * width
        ax.bar(x + offset, vals, width, color=color, edgecolor="black",
               alpha=0.85, label=label)
        # Annotate values
        for xi, v in zip(x + offset, vals):
            if not np.isnan(v):
                ax.text(xi, v + 0.3, f"{v:.1f}", ha="center", va="bottom", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(pieces)
    ax.set_ylabel("Integrated loudness LUFS-I (multichannel)")
    ax.grid(True, axis="y", alpha=0.3, linestyle=":")
    ax.legend(loc="lower right", fontsize=9)
    ax.set_ylim(-30, 0)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(out_path.with_suffix(f".{ext}"), dpi=300, bbox_inches="tight")
    plt.close(fig)


def figure_directional(metrics, out_path):
    """First-order X/Y/Z over W bar chart (Franck recording)."""
    mics = [
        ("ZM-1 (3OA)",    "ZMOneFranck",         COLOR_ZM),
        ("Spcmic (3OA)",  "SpcmicThreeOAFranck", COLOR_SP3),
        ("Spcmic (5OA)",  "SpcmicFiveOAFranck",  COLOR_SP5),
    ]
    components = [("X (front-back)", "X_over_W"),
                  ("Y (left-right)", "Y_over_W"),
                  ("Z (up-down)",    "Z_over_W")]

    fig, ax = plt.subplots(figsize=(6.0, 3.6))
    x = np.arange(len(components))
    width = 0.27
    for i, (label, key, color) in enumerate(mics):
        rec = metrics.get(key)
        if rec is None:
            continue
        vals = [rec[c[1]] for c in components]
        offset = (i - 1) * width
        ax.bar(x + offset, vals, width, color=color, edgecolor="black",
               alpha=0.85, label=label)
        for xi, v in zip(x + offset, vals):
            ax.text(xi, v + 0.01, f"{v:.2f}", ha="center", va="bottom", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels([c[0] for c in components])
    ax.set_ylabel("First-order RMS / W-channel RMS")
    ax.grid(True, axis="y", alpha=0.3, linestyle=":")
    ax.legend(loc="upper right", fontsize=9)
    ax.set_ylim(0, 1.0)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(out_path.with_suffix(f".{ext}"), dpi=300, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Lightweight per-file analysis (mirrors analyze_paper.run_analysis)
# ---------------------------------------------------------------------------
def collect_metrics(base_dir):
    metrics = {}
    print(f"[i] Reading {len(RECORDINGS)} files from {base_dir}")
    for key, session, fname, mic, fmt, piece in RECORDINGS:
        path = base_dir / session / "render" / fname
        if not path.exists():
            print(f"[!] Missing: {path}")
            metrics[key] = None
            continue
        print(f"  - {key}")
        sr, n_channels, n_frames, ssum, w = stream_file(path)
        max_order = 5 if n_channels >= 36 else 3 if n_channels >= 16 else 1 if n_channels >= 4 else 0
        rms = np.sqrt(ssum / n_frames)
        rec = {
            "mic": mic, "format": fmt, "piece": piece,
            "max_order": max_order,
            "order_dbfs": order_energies_dbfs(ssum, n_frames, n_channels, max_order),
        }
        if n_channels >= 4:
            rec["W_rms"] = float(rms[0])
            rec["X_over_W"] = float(rms[3] / rms[0])
            rec["Y_over_W"] = float(rms[1] / rms[0])
            rec["Z_over_W"] = float(rms[2] / rms[0])
        f, db = w_psd_db(w, sr)
        db = smooth_octave(f, db, fraction=6)
        db = reference_normalize(f, db)
        rec["_freqs"] = f
        rec["_w_psd_db_norm"] = db
        lufs_mc, _, _ = lufs_from_reaper_html(path)
        rec["lufs_i_multichannel"] = lufs_mc
        metrics[key] = rec
    return metrics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-dir", type=Path, default=DEFAULT_BASE)
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parent / "paper_results")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    metrics = collect_metrics(args.base_dir)

    print("[i] Drawing figures")
    figure_spatial_energy(metrics, args.out / "fig_spatial_energy")
    figure_spectral(metrics, args.out / "fig_spectral")
    figure_lufs(metrics, args.out / "fig_lufs")
    figure_directional(metrics, args.out / "fig_directional")

    print(f"[OK] Wrote figures to {args.out}/")
    for p in sorted(args.out.glob("fig_*")):
        print(f"     {p.name}")


if __name__ == "__main__":
    main()
