#!/usr/bin/env python3
"""Calculate corpus statistics from render_stats_all.csv"""
import csv
import os
from pathlib import Path
import yaml

DATA_DIR = Path(__file__).parent.parent / "data"
# Audio location: set the HOA_CORPUS_DIR environment variable to the directory
# holding the corpus session folders (download from doi.org/10.34808/5xe2-ah94).
# The path below is only the original authoring machine's default.
PNY_DIR = Path(os.environ.get("HOA_CORPUS_DIR", "/Volumes/PNY 1TB/HOA recordings by BM - all"))

def main():
    dur_1oa = dur_3oa = dur_5oa = 0
    count_1oa = count_3oa = count_5oa = 0
    size_1oa = size_3oa = size_5oa = 0
    
    with open(DATA_DIR / "render_stats_all.csv") as f:
        for row in csv.DictReader(f):
            fn = row["filename"]
            dur = float(row["duration_seconds"])
            session = row["session"]
            
            # Get actual file size from disk
            wav_path = PNY_DIR / session / fn
            file_size = wav_path.stat().st_size if wav_path.exists() else 0
            
            if fn.startswith("1OA"):
                dur_1oa += dur
                count_1oa += 1
                size_1oa += file_size
            elif fn.startswith("3OA"):
                dur_3oa += dur
                count_3oa += 1
                size_3oa += file_size
            elif fn.startswith("5OA"):
                dur_5oa += dur
                count_5oa += 1
                size_5oa += file_size

    def fmt_dur(s):
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        return f"{h}h {m}min"
    
    def fmt_gb(b):
        return f"{b / (1024**3):.1f}"

    print("=" * 60)
    print("CORPUS STATISTICS FROM render_stats_all.csv")
    print("(Actual file sizes from PNY drive)")
    print("=" * 60)
    print(f"\n1OA: {count_1oa} files, {fmt_dur(dur_1oa)}, {fmt_gb(size_1oa)} GB")
    print(f"3OA: {count_3oa} files, {fmt_dur(dur_3oa)}, {fmt_gb(size_3oa)} GB")
    print(f"5OA: {count_5oa} files, {fmt_dur(dur_5oa)}, {fmt_gb(size_5oa)} GB")
    
    total_files = count_1oa + count_3oa + count_5oa
    total_dur = dur_1oa + dur_3oa + dur_5oa
    total_size = size_1oa + size_3oa + size_5oa
    
    print(f"\nTOTAL: {total_files} files, {fmt_dur(total_dur)}, {fmt_gb(total_size)} GB")
    print("=" * 60)
    
    # Count by content type
    print("\n" + "=" * 60)
    print("BY CONTENT TYPE")
    print("=" * 60)
    
    # Load content types from YAML
    metadata_dir = DATA_DIR / "metadata"
    session_ct = {}
    for yaml_file in metadata_dir.glob("*.yaml"):
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        session_ct[yaml_file.stem] = data.get("content_type", "unknown")
    
    # Count files by content type
    ct_files = {}
    ct_sessions = {}
    with open(DATA_DIR / "render_stats_all.csv") as f:
        for row in csv.DictReader(f):
            session = row["session"]
            ct = session_ct.get(session, "unknown")
            ct_files[ct] = ct_files.get(ct, 0) + 1
            if ct not in ct_sessions:
                ct_sessions[ct] = set()
            ct_sessions[ct].add(session)
    
    # Group for Table 4
    groups = {
        "Solo piano": ["solo_piano", "piano_duet"],
        "Choir": ["choir", "choir_with_ensemble", "choir_with_orchestra", "choir_with_soloists"],
        "Chamber music": ["chamber", "ensemble"],
        "Orchestra": ["orchestra"],
        "VR film production": ["vr_film_production"],
        "Outdoor/Ambient": ["ambient"],
    }
    
    print("\nFor Table 4 (Corpus Composition by Content Type):")
    print("-" * 50)
    grand_total_files = 0
    grand_total_sessions = 0
    for group_name, cts in groups.items():
        files = sum(ct_files.get(ct, 0) for ct in cts)
        sessions = set()
        for ct in cts:
            sessions.update(ct_sessions.get(ct, set()))
        print(f"{group_name}: {len(sessions)} sessions, {files} files")
        grand_total_files += files
        grand_total_sessions += len(sessions)
    print("-" * 50)
    print(f"TOTAL: {grand_total_sessions} sessions, {grand_total_files} files")

if __name__ == "__main__":
    main()
