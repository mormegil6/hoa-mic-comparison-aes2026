# Analysis pipeline — AES Submission 51

Single-source, reproducible analysis for `main_submission51-ZM1vsSpcmic.tex`.

## Layout

```
analysis_data/
├── analyze_paper.py            # WAV  -> CSV + paper_variables.tex (numbers)
├── plot_paper.py               # WAV  -> PNG/PDF figures
├── check_aliasing_band.py      # diagnostic: sub-aliasing rolloff sweep
├── paper_results/              # outputs of analyze_paper / plot_paper
├── render_stats/               # REAPER's *.render_stats.html (LUFS source)
├── metadata/                   # session YAMLs (April 30 + August 15)
├── _wav_sources/               # symlinks to the external HOA drive
└── (../__archive/)             # legacy corpus scripts/plots, one level up
```

## Reproducibility workflow

1. Plug in the external HOA drive (`/Volumes/PNY 1TB/...`) or pass another
   path via `--base /path/to/recordings`.
2. Run the two scripts:

   ```bash
   python3 analyze_paper.py        # numbers (~5 minutes)
   python3 plot_paper.py           # figures  (~5 minutes)
   ```

3. Compile the paper. The manuscript imports
   `paper_results/paper_variables.tex`, so all numeric claims update
   automatically.

## What goes in the paper

| In paper                                  | LaTeX command                          | Source                |
|-------------------------------------------|----------------------------------------|-----------------------|
| Session durations                         | `\AugFifteenDurMin`, `\AprThirtyDurMin`| WAV header            |
| Spectral elevation 200–600 Hz             | `\SpectralEle{Min,Max,Mean}`           | W-PSD, Welch          |
| LUFS-I delta (paper's headline)           | `\LUFSDeltaMC{Min,Max}`                | REAPER multichannel   |
| LUFS-I delta (W-only sanity)              | `\LUFSDeltaW{Min,Max}`                 | BS.1770-5 in-script   |
| Spatial energy rolloff (Franck)           | `\Rolloff{ZMOne,SpcmicThreeOA}Franck`  | per-order RMS         |
| Rolloff gap                               | `\RolloffDeltaFranck`                  | derived               |
| Directional X/W ratio                     | `\DirX{ZMOne,SpcmicThreeOA}Franck`     | first-order RMS       |
| Sub-aliasing rolloff gap (<3 kHz)         | `\RolloffDeltaSubAlias`                | Welch PSD, band sum   |

## Methodology notes

- **LUFS** is reported under two definitions. The headline number
  (`\LUFSDeltaMC*`) parses REAPER's `*.render_stats.html` and reflects a
  multichannel BS.1770 sum across all rendered Ambisonics channels. The
  secondary number (`\LUFSDeltaW*`) is computed in-script from the W
  channel alone via ITU-R BS.1770-5 K-weighting + gating; it inverts sign
  because the Spcmic's loudness lead lives in the higher-order channels,
  not in the omnidirectional pressure.
- **Spatial energy** per order = linear-mean per-channel RMS within the
  order's ACN range, expressed in dBFS. Same definition as
  `pub_fig09_spatial_energy.csv` in the corpus repo.
- **Directional ratios** = X/W, Y/W, Z/W of channel-RMS values (ACN
  ordering: 0=W, 1=Y, 2=Z, 3=X). Computed across the full piece.
- **Sub-aliasing check** (`\RolloffDeltaSubAlias`) re-runs the spatial-
  energy calculation using only Welch PSD bins below ~3 kHz (Pinardi
  et al. 2021 give the ZM-1 a 3rd-order usable band of 660--3080 Hz).
  The headline 19 dB rolloff gap survives the band limit (it actually
  grows slightly to 19.3 dB), confirming the finding reflects order-
  truncation rather than spatial aliasing.

The Spcmic 3OA and 5OA renders are produced by different Spcmic plugin
builds (3OA = 0.9.1β, 5OA = 1.0.2α) so their first four channels differ
by a few thousandths in amplitude; the resulting X/W ratios differ by
$\approx$0.003 — irrelevant to the conclusions.
