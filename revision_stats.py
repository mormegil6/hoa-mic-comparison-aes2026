#!/usr/bin/env python3
"""
revision_stats.py
=================

Statistical supplement for the IEEE Access revision of the HOA corpus paper
(manuscript Access-2026-28350), extending analyze_paper.py with uncertainty
estimates requested by Reviewers 3 and 4.

Method
------
Each recording of the co-located comparison session (2024-08-15) is streamed
in 1-second frames; per-frame per-channel sums of squares are cached. All
arrays recorded the same performance simultaneously, so frames are paired
across arrays by wall-clock time. A paired moving-block bootstrap (block
length 30 s, 2000 replicates, fixed seed) resamples frame indices — the SAME
indices for both arrays of a pair — and recomputes the per-order RMS levels
(identical definition to analyze_paper.order_energies_dbfs), the 0th-to-3rd
order rolloff of each array, and the between-array rolloff difference for
each replicate. Percentile 95% confidence intervals are reported.

The block bootstrap respects the strong temporal correlation of musical
material; the paired design removes the shared programme-level variance.
The resulting CI quantifies measurement uncertainty of the reported
differences WITHIN this session; it deliberately does not claim
generalization across venues or sessions.

Outputs (revision_results/)
---------------------------
  cache/frames_<key>.npz              per-frame per-channel energy cache
  spatial_energy_two_piece.csv        per-order dBFS + 95% CI, all arrays x pieces
  rolloff_bootstrap.csv               rolloff + difference CIs
  directional_ci.csv                  W dBFS and X/Y/Z-over-W with 95% CIs
  frame_order_energies_<key>.csv      frame-level per-order dBFS (release artifact)
  frame_difference_3OA_<piece>.csv    frame-level ZM-1 vs Spcmic 3OA difference file
  revision_stats_variables.tex        \\newcommand definitions for the manuscript

Usage:
    python revision_stats.py --base-dir "/Volumes/PNY 1TB/HOA recordings by BM - all"
"""

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf

from analyze_paper import ORDER_RANGES, SESSION_AUG15

FRAME_SECONDS = 1.0
BLOCK_SECONDS = 30
N_BOOT = 2000
SEED = 2026
CI_LO, CI_HI = 2.5, 97.5

# (key, filename, mic, format, piece) — comparison session only, incl. SR-VRMIC
RECORDINGS = [
    ("ZMOneFranck",            "3OA_ZM1_CFranck-PreludeChoralFugue.wav",     "ZM-1",     "3OA", "Franck"),
    ("ZMOneProkofiev",         "3OA_ZM1_SProkofiev-Sonata4.wav",             "ZM-1",     "3OA", "Prokofiev"),
    ("SpcmicThreeOAFranck",    "3OA_Spcmic_CFranck-PreludeChoralFugue.wav",  "Spcmic",   "3OA", "Franck"),
    ("SpcmicThreeOAProkofiev", "3OA_Spcmic_SProkofiev-Sonata4.wav",          "Spcmic",   "3OA", "Prokofiev"),
    ("SpcmicFiveOAFranck",     "5OA_Spcmic_CFranck-PreludeChoralFugue.wav",  "Spcmic",   "5OA", "Franck"),
    ("SpcmicFiveOAProkofiev",  "5OA_Spcmic_SProkofiev-Sonata4.wav",          "Spcmic",   "5OA", "Prokofiev"),
    ("SRVRMICFranck",          "1OA_SRVRMIC_CFranck-PreludeChoralFugue.wav", "SR-VRMIC", "1OA", "Franck"),
    ("SRVRMICProkofiev",       "1OA_SRVRMIC_SProkofiev-Sonata4.wav",         "SR-VRMIC", "1OA", "Prokofiev"),
]

PAIRS = [  # paired bootstrap: ZM-1 vs Spcmic, same piece, both at 3OA
    ("Franck",    "ZMOneFranck",    "SpcmicThreeOAFranck"),
    ("Prokofiev", "ZMOneProkofiev", "SpcmicThreeOAProkofiev"),
]

MIC_LABEL = {
    "ZMOneFranck": "ZM-1 (3OA)", "ZMOneProkofiev": "ZM-1 (3OA)",
    "SpcmicThreeOAFranck": "Spcmic (3OA)", "SpcmicThreeOAProkofiev": "Spcmic (3OA)",
    "SpcmicFiveOAFranck": "Spcmic (5OA)", "SpcmicFiveOAProkofiev": "Spcmic (5OA)",
    "SRVRMICFranck": "SR-VRMIC (1OA)", "SRVRMICProkofiev": "SR-VRMIC (1OA)",
}


def max_order_for(n_channels):
    return 5 if n_channels >= 36 else 3 if n_channels >= 16 else 1


def build_frame_cache(path, cache_path):
    """Stream a WAV in 1-s frames; cache per-frame per-channel sum of squares."""
    if cache_path.exists():
        z = np.load(cache_path)
        return z["energy"], z["counts"], int(z["sr"])
    info = sf.info(str(path))
    sr, n_ch = info.samplerate, info.channels
    frame_len = int(round(sr * FRAME_SECONDS))
    energies, counts = [], []
    with sf.SoundFile(str(path)) as f:
        for block in f.blocks(blocksize=frame_len, dtype="float32"):
            if block.ndim == 1:
                block = block.reshape(-1, 1)
            energies.append(np.sum(block.astype(np.float64) ** 2, axis=0))
            counts.append(block.shape[0])
    energy = np.vstack(energies)
    counts = np.asarray(counts, dtype=np.int64)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache_path, energy=energy, counts=counts, sr=sr)
    return energy, counts, sr


def order_levels_from_selection(energy, counts, sel, max_order):
    """Per-order dBFS from selected frame indices; identical metric to
    analyze_paper.order_energies_dbfs (linear mean of per-channel RMS)."""
    ssum = energy[sel].sum(axis=0)
    n = counts[sel].sum()
    rms = np.sqrt(ssum / n)
    out = {}
    for order in range(max_order + 1):
        s, e = ORDER_RANGES[order]
        if e <= len(rms):
            out[order] = 20.0 * np.log10(float(np.mean(rms[s:e])) + 1e-20)
    return out


def directional_from_selection(energy, counts, sel):
    ssum = energy[sel].sum(axis=0)
    n = counts[sel].sum()
    rms = np.sqrt(ssum / n)
    w = rms[0]
    return {
        "W_dBFS": 20.0 * np.log10(w + 1e-20),
        # ACN: 0=W, 1=Y, 2=Z, 3=X
        "X_over_W": float(rms[3] / w),
        "Y_over_W": float(rms[1] / w),
        "Z_over_W": float(rms[2] / w),
    }


def block_bootstrap_indices(rng, n, block_len, n_boot):
    """Yield n_boot arrays of frame indices from a moving-block bootstrap."""
    n_blocks = int(np.ceil(n / block_len))
    starts_max = n - block_len
    for _ in range(n_boot):
        starts = rng.integers(0, starts_max + 1, size=n_blocks)
        idx = (starts[:, None] + np.arange(block_len)[None, :]).ravel()[:n]
        yield idx


def pct_ci(values):
    return float(np.percentile(values, CI_LO)), float(np.percentile(values, CI_HI))


def fmt(v, d=1):
    return f"{v:.{d}f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parent / "revision_results")
    args = ap.parse_args()

    render_dir = args.base_dir / SESSION_AUG15 / "render"
    args.out.mkdir(parents=True, exist_ok=True)
    cache_dir = args.out / "cache"

    # Audio is only needed for recordings whose frame cache is missing: with the
    # committed caches present, the whole analysis reproduces without the WAV files.
    missing = [f for k, f, *_ in RECORDINGS
               if not (cache_dir / f"frames_{k}.npz").exists()]
    if missing and not render_dir.exists():
        print(f"[!] Frame caches missing for {len(missing)} recording(s) and no audio "
              f"at {render_dir}\n[!] Pass --base-dir pointing at the corpus download "
              f"(doi.org/10.34808/5xe2-ah94).", file=sys.stderr)
        sys.exit(1)

    rng = np.random.default_rng(SEED)
    caches = {}
    print(f"[i] Frame caches in {cache_dir}"
          + (f"; reading audio from {render_dir}" if missing else " (complete, no audio needed)"))
    for key, fname, mic, fmt_, piece in RECORDINGS:
        path = render_dir / fname
        if not path.exists() and not (cache_dir / f"frames_{key}.npz").exists():
            print(f"[!] Missing: {path}", file=sys.stderr)
            sys.exit(1)
        print(f"  - {key}")
        energy, counts, sr = build_frame_cache(path, cache_dir / f"frames_{key}.npz")
        caches[key] = dict(energy=energy, counts=counts, sr=sr,
                           mic=mic, format=fmt_, piece=piece,
                           max_order=max_order_for(energy.shape[1]))

    # ---------------- per-file: point estimates + single-array bootstrap ----
    spatial_rows, dir_rows = [], []
    per_order_ci = {}      # key -> {order: (lo, hi)}
    rolloff_ci = {}        # key -> (pt, lo, hi)
    dir_ci = {}            # key -> {stat: (pt, lo, hi)}
    block_len = int(round(BLOCK_SECONDS / FRAME_SECONDS))

    for key, c in caches.items():
        n_full = int(np.sum(c["counts"] == c["counts"].max()))
        all_idx = np.arange(len(c["counts"]))
        full_idx = np.arange(n_full)  # frames of full length (trailing partial dropped for CI)
        pt_orders = order_levels_from_selection(c["energy"], c["counts"], all_idx, c["max_order"])
        pt_dir = directional_from_selection(c["energy"], c["counts"], all_idx)

        boot_orders = {o: [] for o in pt_orders}
        boot_roll = []
        boot_dir = {k: [] for k in pt_dir}
        for idx in block_bootstrap_indices(rng, n_full, block_len, N_BOOT):
            sel = full_idx[idx]
            ords = order_levels_from_selection(c["energy"], c["counts"], sel, c["max_order"])
            for o, v in ords.items():
                boot_orders[o].append(v)
            if 0 in ords and 3 in ords:
                boot_roll.append(ords[0] - ords[3])
            d = directional_from_selection(c["energy"], c["counts"], sel)
            for k, v in d.items():
                boot_dir[k].append(v)

        per_order_ci[key] = {o: pct_ci(v) for o, v in boot_orders.items()}
        if boot_roll:
            rolloff_ci[key] = (pt_orders[0] - pt_orders[3], *pct_ci(boot_roll))
        dir_ci[key] = {k: (pt_dir[k], *pct_ci(v)) for k, v in boot_dir.items()}

        row = {"key": key, "microphone": MIC_LABEL[key], "mic": c["mic"],
               "format": c["format"], "piece": c["piece"],
               "max_order": c["max_order"]}
        for o in range(6):
            if o in pt_orders:
                lo, hi = per_order_ci[key][o]
                row[f"order{o}_dBFS"] = f"{pt_orders[o]:.3f}"
                row[f"order{o}_ci_lo"] = f"{lo:.3f}"
                row[f"order{o}_ci_hi"] = f"{hi:.3f}"
        if key in rolloff_ci:
            pt, lo, hi = rolloff_ci[key]
            row["rolloff_0_to_3_dB"] = f"{pt:.3f}"
            row["rolloff_ci_lo"] = f"{lo:.3f}"
            row["rolloff_ci_hi"] = f"{hi:.3f}"
        spatial_rows.append(row)

        drow = {"key": key, "microphone": MIC_LABEL[key], "piece": c["piece"]}
        for k in ("W_dBFS", "X_over_W", "Y_over_W", "Z_over_W"):
            pt, lo, hi = dir_ci[key][k]
            drow[k] = f"{pt:.4f}"
            drow[f"{k}_ci_lo"] = f"{lo:.4f}"
            drow[f"{k}_ci_hi"] = f"{hi:.4f}"
        dir_rows.append(drow)

        # frame-level release artifact
        with open(args.out / f"frame_order_energies_{key}.csv", "w", newline="") as f:
            orders = sorted(pt_orders)
            w = csv.writer(f)
            w.writerow(["t_start_s"] + [f"order{o}_dBFS" for o in orders])
            for i in all_idx:
                ords = order_levels_from_selection(c["energy"], c["counts"],
                                                  np.array([i]), c["max_order"])
                w.writerow([f"{i * FRAME_SECONDS:.1f}"] +
                           [f"{ords[o]:.3f}" for o in orders])

    # ---------------- paired bootstrap: rolloff difference ------------------
    roll_rows = []
    paired = {}
    for piece, kz, ks in PAIRS:
        cz, cs = caches[kz], caches[ks]
        n = min(int(np.sum(cz["counts"] == cz["counts"].max())),
                int(np.sum(cs["counts"] == cs["counts"].max())))
        pt_z = order_levels_from_selection(cz["energy"], cz["counts"],
                                           np.arange(len(cz["counts"])), 3)
        pt_s = order_levels_from_selection(cs["energy"], cs["counts"],
                                           np.arange(len(cs["counts"])), 3)
        pt_diff = (pt_z[0] - pt_z[3]) - (pt_s[0] - pt_s[3])
        boots = []
        for idx in block_bootstrap_indices(rng, n, block_len, N_BOOT):
            oz = order_levels_from_selection(cz["energy"], cz["counts"], idx, 3)
            os_ = order_levels_from_selection(cs["energy"], cs["counts"], idx, 3)
            boots.append((oz[0] - oz[3]) - (os_[0] - os_[3]))
        lo, hi = pct_ci(boots)
        se = float(np.std(boots, ddof=1))
        paired[piece] = (pt_diff, lo, hi, se)
        roll_rows.append({"comparison": f"ZM1_minus_Spcmic3OA_{piece}",
                          "point_dB": f"{pt_diff:.3f}", "ci_lo": f"{lo:.3f}",
                          "ci_hi": f"{hi:.3f}", "bootstrap_se": f"{se:.3f}",
                          "n_frames": n, "block_s": BLOCK_SECONDS,
                          "replicates": N_BOOT})

        # frame-level difference file (R1's suggestion, 3OA pair)
        n_all = min(len(cz["counts"]), len(cs["counts"]))
        with open(args.out / f"frame_difference_3OA_{piece}.csv", "w", newline="") as f:
            w = csv.writer(f)
            hdr = ["t_start_s"]
            for tag in ("zm1", "spcmic"):
                hdr += [f"{tag}_order{o}_dBFS" for o in range(4)]
            hdr += [f"diff_order{o}_dB" for o in range(4)]
            w.writerow(hdr)
            for i in range(n_all):
                oz = order_levels_from_selection(cz["energy"], cz["counts"],
                                                 np.array([i]), 3)
                os_ = order_levels_from_selection(cs["energy"], cs["counts"],
                                                  np.array([i]), 3)
                w.writerow([f"{i * FRAME_SECONDS:.1f}"] +
                           [f"{oz[o]:.3f}" for o in range(4)] +
                           [f"{os_[o]:.3f}" for o in range(4)] +
                           [f"{oz[o] - os_[o]:.3f}" for o in range(4)])

    for key, (pt, lo, hi) in rolloff_ci.items():
        roll_rows.append({"comparison": f"rolloff_0_3_{key}",
                          "point_dB": f"{pt:.3f}", "ci_lo": f"{lo:.3f}",
                          "ci_hi": f"{hi:.3f}", "bootstrap_se": "",
                          "n_frames": len(caches[key]["counts"]),
                          "block_s": BLOCK_SECONDS, "replicates": N_BOOT})

    # ---------------- writers ----------------------------------------------
    def write_rows(path, rows):
        keys = []
        for r in rows:
            for k in r:
                if k not in keys:
                    keys.append(k)
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)

    write_rows(args.out / "spatial_energy_two_piece.csv", spatial_rows)
    write_rows(args.out / "directional_ci.csv", dir_rows)
    write_rows(args.out / "rolloff_bootstrap.csv", roll_rows)

    # ---------------- LaTeX variables ---------------------------------------
    lines = ["% Auto-generated by revision_stats.py - do not edit by hand.",
             f"% Generated: {datetime.now().isoformat(timespec='seconds')}",
             f"% Paired moving-block bootstrap: {FRAME_SECONDS:.0f}-s frames, "
             f"{BLOCK_SECONDS}-s blocks, {N_BOOT} replicates, seed {SEED}.", ""]

    def cmd(name, value):
        lines.append(f"\\newcommand{{\\{name}}}{{{value}}}")

    cmd("StatsFrameSeconds", f"{FRAME_SECONDS:.0f}")
    cmd("StatsBlockSeconds", f"{BLOCK_SECONDS}")
    cmd("StatsBootstrapReplicates", f"{N_BOOT}")
    lines.append("")
    for key, (pt, lo, hi) in rolloff_ci.items():
        cmd(f"Rolloff{key}Pt", fmt(pt))
        cmd(f"Rolloff{key}CILo", fmt(lo))
        cmd(f"Rolloff{key}CIHi", fmt(hi))
    lines.append("")
    for piece, (pt, lo, hi, se) in paired.items():
        cmd(f"RolloffDelta{piece}Pt", fmt(pt))
        cmd(f"RolloffDelta{piece}CILo", fmt(lo))
        cmd(f"RolloffDelta{piece}CIHi", fmt(hi))
        cmd(f"RolloffDelta{piece}SE", fmt(se, 2))
    lines.append("")
    for key in ("ZMOneFranck", "SpcmicThreeOAFranck",
                "ZMOneProkofiev", "SpcmicThreeOAProkofiev"):
        for comp in ("X", "Y", "Z"):
            pt, lo, hi = dir_ci[key][f"{comp}_over_W"]
            cmd(f"Dir{comp}{key}Pt", fmt(pt, 2))
            cmd(f"Dir{comp}{key}CILo", fmt(lo, 2))
            cmd(f"Dir{comp}{key}CIHi", fmt(hi, 2))
    (args.out / "revision_stats_variables.tex").write_text("\n".join(lines) + "\n")

    print(f"\n[OK] Wrote {args.out}/")
    for p in sorted(args.out.iterdir()):
        print(f"     {p.name}")


if __name__ == "__main__":
    main()
