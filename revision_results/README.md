# Revision results — bootstrap uncertainty analysis

Outputs of `../revision_stats.py`, added during peer review of the IEEE Access corpus
paper to attach uncertainty estimates to the microphone-comparison results.

## Resampling design

Each recording of the co-located session (2024-08-15) is streamed in **1-second frames**
and the per-frame, per-channel sum of squares is cached. Because all three arrays
recorded the same performance simultaneously, frames are **paired across arrays by
wall-clock time**: a bootstrap replicate resamples the *same* frame indices for both
arrays of a pair, so the programme-level variance shared by both cancels and the
resulting interval reflects the between-array difference alone.

Resampling uses a **moving-block bootstrap** (30-second blocks, 2000 replicates,
fixed seed 2026), which respects the strong temporal correlation of musical material —
an i.i.d. frame bootstrap would badly understate the interval. Per-order levels are
recomputed per replicate with exactly the definition used in `analyze_paper.py`
(`order_energies_dbfs`: linear mean of per-channel RMS within each Ambisonics order),
so point estimates match the main analysis to the last decimal.

**Scope**: these intervals quantify measurement uncertainty *within* the comparison
session. They are not a claim about generalization across venues, source types, or
source distances — the manuscript's Limitations section states this explicitly.

## Files

| File | Contents |
|---|---|
| `spatial_energy_two_piece.csv` | Per-order dBFS with 95% CIs, every array × both pieces |
| `rolloff_bootstrap.csv` | 0th-to-3rd rolloff per array and the **paired** between-array difference, with CI and bootstrap SE |
| `directional_ci.csv` | W level and X/Y/Z-over-W ratios with 95% CIs |
| `revision_stats_variables.tex` | `\newcommand` macros consumed by the manuscript |
| `frame_order_energies_<key>.csv` | Frame-level per-order dBFS for each recording |
| `frame_difference_3OA_<piece>.csv` | Annotated frame-level ZM-1 vs Spcmic difference file (per order) |
| `figures/` | Two-piece Fig. 9 and Figs 10a/10b rendered with CI whiskers |
| `cache/frames_<key>.npz` | Per-frame per-channel energy caches (see below) |

## Headline numbers

| Quantity | Point estimate | 95% CI |
|---|---|---|
| ZM-1 rolloff 0→3, Franck | 27.4 dB | 27.0–28.3 |
| ZM-1 rolloff 0→3, Prokofiev | 26.0 dB | 25.4–27.1 |
| Spcmic (3OA) rolloff 0→3, both pieces | 8.4 / 8.5 dB | width < 0.1 dB |
| **Paired difference, Franck** | **19.0 dB** | **18.5–19.8** (SE 0.34) |
| **Paired difference, Prokofiev** | **17.5 dB** | **16.9–18.6** (SE 0.45) |

## Reproducing without the audio

The `cache/*.npz` frame-energy caches are committed (≈1.2 MB total), so the bootstrap,
the derived CSVs, and the figures can be regenerated **without downloading the ~48 GB
of session audio**. Re-running `revision_stats.py` reuses any cache it finds and only
streams WAV files whose cache is missing:

```sh
python3 ../revision_stats.py --base-dir /any/path    # caches present -> no audio read
python3 ../revision_figures.py
```

To rebuild the caches from the audio, delete `cache/` and pass the real corpus path
(download from [doi.org/10.34808/5xe2-ah94](https://doi.org/10.34808/5xe2-ah94)).

## Frame-level difference files

`frame_difference_3OA_<piece>.csv` gives, for every 1-second frame, the per-order dBFS
of the ZM-1 and the Spcmic and their difference — a directly usable annotation of the
matched-capture space (both arrays, identical performance, identical acoustic position)
for machine-learning work that would otherwise require audio-level preprocessing.
