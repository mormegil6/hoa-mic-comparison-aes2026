[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)]() [![numpy](https://img.shields.io/badge/numpy-1.24+-blue.svg)]() [![scipy](https://img.shields.io/badge/scipy-1.11+-blue.svg)]() [![soundfile](https://img.shields.io/badge/soundfile-0.12+-blue.svg)]() [![matplotlib](https://img.shields.io/badge/matplotlib-3.7+-blue.svg)]() [![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)

# ZM-1 vs Spcmic - HOA Recording Performance Analysis

Supplementary materials for the paper: **"Zylia ZM-1 vs. Harpex Spcmic: A Case Study of Higher-Order Ambisonic Recording Performance"**

This repository contains:
- Reproducible analysis pipeline (Python scripts)
- Session metadata (two recording sessions)
- Pre-computed results (CSV tables, LaTeX macros, publication figures)
- Final submission PDFs (paper + poster)

For methodology, interpretation, and results discussion, please refer to the main paper.

## Repository Structure

```
.
├── analyze_paper.py                        # Single-source analysis script
├── plot_paper.py                           # Figure generation (called from analyze_paper.py)
├── check_aliasing_band.py                  # Spatial-aliasing band verification
├── EP51_paper.pdf                          # Final submitted paper (AES Convention 160, Express Paper 51)
├── EP51_poster.pdf                         # Final submitted poster (AES Convention 160, Express Paper 51)
├── metadata/
│   ├── 2024.04.30_metadata_public.yaml     # April 2024 session (Ginastera)
│   └── 2024.08.15_metadata_public.yaml     # August 2024 session (Franck, Prokofiev)
├── paper_results/
│   ├── per_file_metrics.csv
│   ├── spectral_band_diff.csv
│   ├── lufs_pairs.csv
│   ├── spatial_energy.csv
│   ├── directional.csv
│   ├── paper_variables.tex
│   ├── fig_*.pdf
│   ├── fig_*.png
│   ├── recording1_photo1.jpg
│   ├── recording1_photo2.jpg
│   ├── recording2_photo1.jpg
│   └── recording2_photo2.jpg
├── LICENSE
└── README.md
```

## Recordings

**Recording corpus**: Higher-Order Ambisonics Recording Corpus, deposited at *Bridge of Data* (Most Danych), Gdańsk University of Technology - [doi.org/10.34808/5xe2-ah94](https://doi.org/10.34808/5xe2-ah94) (CC BY-NC-SA 4.0)

The recordings are not included in this repository. Download them separately from the DOI above and point the analysis script to their location with `--base-dir`.

Two recording sessions at the Main Aula of Gdańsk University of Technology (RT60 ≈ 1.97 s):

**Session 1** - 2024-08-15 · Microphone comparison (ZM-1, Spcmic, Saramonic SR-VRMIC)
- Repertoire: César Franck - *Prélude, Choral et Fugue*; Sergei Prokofiev - *Piano Sonata No. 4 in C minor, Op. 29*
- Performer: Piotr Pawlak (piano)

**Session 2** - 2024-04-30 · Microphone comparison (ZM-1, Spcmic)
- Repertoire: Alberto Ginastera - *Piano Sonata No. 1, Op. 22*
- Performer: Mikołaj Sikała (piano)

## What `analyze_paper.py` Computes

The script reads rendered B-format WAV files and writes:

| Output file | Contents |
|---|---|
| `paper_results/per_file_metrics.csv` | Per-file RMS / order energies / LUFS |
| `paper_results/spectral_band_diff.csv` | ZM-1 minus Spcmic W-PSD per frequency |
| `paper_results/lufs_pairs.csv` | LUFS deltas per (mic, piece) |
| `paper_results/spatial_energy.csv` | Per-order dBFS, rolloff, delta |
| `paper_results/directional.csv` | X/W, Y/W, Z/W ratios per file |
| `paper_results/paper_variables.tex` | `\newcommand` definitions consumed by the manuscript |
| `paper_results/fig_*.pdf` | Publication figures (vector, for the paper) |
| `paper_results/fig_*.png` | Publication figures (raster previews) |
| `paper_results/recording1_photo1.jpg` | Recording session 1 - photo 1 |
| `paper_results/recording1_photo2.jpg` | Recording session 1 - photo 2 |
| `paper_results/recording2_photo1.jpg` | Recording session 2 - photo 1 |
| `paper_results/recording2_photo2.jpg` | Recording session 2 - photo 2 |

The manuscript imports `paper_variables.tex` via `\input{}` - every numeric claim is written as a macro, so re-running `analyze_paper.py` and recompiling LaTeX is the complete reproducibility loop.

LUFS-I is computed in-script via ITU-R BS.1770-5 K-weighting on the W channel; no dependency on `pyloudnorm` or REAPER render statistics.

## Reproducing the Analysis

### Prerequisites

```sh
pip install numpy scipy soundfile matplotlib pyyaml
```

### Run the Analysis

```sh
python3 analyze_paper.py

# Point to the corpus download location:
python3 analyze_paper.py --base-dir /path/to/hoa-corpus
```

Running `analyze_paper.py` calls `plot_paper.py` automatically. All outputs are written to `paper_results/`.

**Note**: `check_aliasing_band.py` is a standalone verification script that re-computes spatial-energy rolloff restricted to sub-aliasing frequency bins (< 3 kHz). Run it separately if needed:

```sh
python3 check_aliasing_band.py
```

## Citation

If you use this code or the recordings, please cite:

```bibtex
@inproceedings{mroz_zm1_spcmic_2026,
  author    = {Mróz, Bartłomiej and Zaporowski, Szymon},
  title     = {{Zylia ZM-1 vs. Harpex Spcmic: A Case Study of Higher-Order Ambisonic Recording Performance}},
  booktitle = {160th {Audio} {Engineering} {Society} {Convention}},
  address   = {Copenhagen, Denmark},
  month     = may,
  year      = {2026},
  publisher = {Audio Engineering Society},
  copyright = {Creative Commons Attribution 4.0 International License},
  language  = {en},
  url       = {https://aes.org/publications/elibrary-page/?id=23166},
}

@misc{mroz_seven-year_2026,
  author       = {Mróz, Bartłomiej and Zaporowski, Szymon},
  title        = {A {Seven}-{Year} {Corpus} of {Higher}-{Order} {Ambisonics} {Recordings}},
  howpublished = {MOST Danych, Gdańsk University of Technology},
  month        = feb,
  year         = {2026},
  doi          = {10.34808/5XE2-AH94},
  url          = {https://mostwiedzy.pl/en/open-research-data/a-seven-year-corpus-of-higher-order-ambisonics-recordings,205035347247528-0},
  language     = {en},
  urldate      = {2026-05-02},
  publisher    = {Gdańsk University of Technology},
  keywords     = {Ambisonics, B-format, Higher-Order Ambisonics, immersive audio, MEMS microphone, music recording, recording corpus, room acoustics, spatial audio, spherical microphone array}
}
```

## License

**Code in this repository**: licensed under [Creative Commons Attribution 4.0 International License][cc-by].

[![CC BY 4.0][cc-by-image]][cc-by]

[cc-by]: https://creativecommons.org/licenses/by/4.0/
[cc-by-image]: https://i.creativecommons.org/l/by/4.0/88x31.png

## Contact

Bartłomiej Mróz · bartlomiej.mroz@pg.edu.pl · Department of Multimedia Systems, Gdańsk University of Technology
