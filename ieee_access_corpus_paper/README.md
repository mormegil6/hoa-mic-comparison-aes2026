# IEEE Access corpus paper — analysis and figure pipeline

Supplementary code for:

***"A Seven-Year Higher-Order Ambisonics Recording Corpus: Dataset, Methodology, and a Co-Located Spherical Microphone Array Comparison"***
Bartłomiej Mróz, Szymon Zaporowski · *IEEE Access* (under review)

This directory holds the scripts that produce the corpus-wide figures, tables, and
LaTeX macros of that manuscript. The microphone-comparison analysis itself lives in
the repository root (`analyze_paper.py`, `plot_paper.py`, `revision_stats.py`), since
it is shared with the AES Convention paper.

## Contents

```
ieee_access_corpus_paper/
├── pyscripts/
│   ├── analysis_utils.py             # shared config, spectral helpers, mic definitions
│   ├── generate_all_figures.py       # audio-driven: computes every figure CSV
│   ├── render_ieee_figures.py        # CSV-driven: renders Figs 3-10 at IEEE column width
│   ├── generate_latex_variables.py   # CSV -> \newcommand macros consumed by the manuscript
│   ├── parse_render_stats.py         # REAPER render-stats HTML -> LUFS table
│   ├── analyze_aula_acoustics.py     # room-acoustic parameters (RT60, C80, ...)
│   ├── calculate_corpus_stats.py     # corpus size/duration/order inventory
│   ├── generate_session_inventory.py # session inventory LaTeX table
│   ├── plot_rt60.py                  # Fig. 3 standalone
│   ├── plot_lufs_distribution.py     # Fig. 6 standalone
│   └── plot_spectral_comparison.py   # Fig. 7 standalone (needs audio)
├── plots/                            # pre-computed figure inputs (CSV)
└── data/                             # render statistics, aggregated LaTeX macros, inventory table
```

## Reproducing the figures

Most figures regenerate **without downloading any audio**, straight from the CSVs in
`plots/`:

```sh
pip install -r ../requirements.txt
python3 pyscripts/render_ieee_figures.py          # all figures
python3 pyscripts/render_ieee_figures.py 09 10    # selected figure numbers
```

Two exceptions need the audio: Fig. 7 (spectral comparison) and any re-run of
`generate_all_figures.py`, which recomputes the CSVs from the WAV files. Download the
corpus from [doi.org/10.34808/5xe2-ah94](https://doi.org/10.34808/5xe2-ah94) and point
the scripts at it:

```sh
export HOA_CORPUS_DIR="/path/to/hoa-corpus"
python3 pyscripts/generate_all_figures.py
```

`HOA_CORPUS_DIR` must contain the session folders as deposited (e.g.
`2024.08.15 -- ZM1 Spcmic Saramonic/render/*.wav`).

## Numeric claims in the manuscript

Every number cited in the paper is a LaTeX macro, not a typed literal:

```
CSV results  ->  generate_latex_variables.py  ->  data/all_variables.tex  ->  \input{} in the manuscript
```

Re-running the analysis and recompiling the LaTeX is therefore the complete
reproducibility loop; no figure or statistic is transcribed by hand.

## Revision statistics (bootstrap confidence intervals)

The uncertainty analysis added during peer review lives in the repository root:

```sh
cd ..
python3 revision_stats.py --base-dir "$HOA_CORPUS_DIR"   # frame caches + bootstrap CIs
python3 revision_figures.py                              # two-piece Fig. 9, Figs 10a/10b with CIs
```

See `../revision_results/README.md` for the outputs and the resampling design.

## Notes

- Session metadata YAML files are not included here: the source files contain personal
  notes. Public metadata for the two comparison sessions is in `../metadata/`.
- Room-acoustic measurement audio (impulse-response recordings, several hundred MB) is
  not tracked; `plots/pub_fig03_rt60_octave_bands.csv` holds the derived parameters.
