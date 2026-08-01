#!/usr/bin/env python3
"""
Parse LUFS and audio statistics from Reaper render_stats.html files.

Extracts loudness metrics from all rendered WAV files across the corpus
and outputs to CSV and YAML for further analysis.

Author: Bartłomiej Mróz
Date: 2026-01-26
"""

import os
import re
import csv
import yaml
from pathlib import Path
from html.parser import HTMLParser
from datetime import datetime

# Configuration
# Audio location: set the HOA_CORPUS_DIR environment variable to the directory
# holding the corpus session folders (download from doi.org/10.34808/5xe2-ah94).
# The path below is only the original authoring machine's default.
CORPUS_DIR = Path(os.environ.get("HOA_CORPUS_DIR", "/Volumes/PNY 1TB/HOA recordings by BM - all"))
SCRIPT_DIR = Path(__file__).parent.parent
OUTPUT_DIR = SCRIPT_DIR / "data"
OUTPUT_DIR.mkdir(exist_ok=True)


class RenderStatsParser(HTMLParser):
    """Parse Reaper render_stats.html files."""
    
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_tbody = False
        self.in_row = False
        self.in_cell = False
        self.current_row = []
        self.headers = []
        self.rows = []
        self.in_header = False
        
    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.in_table = True
        elif tag == 'thead':
            self.in_header = True
        elif tag == 'tbody':
            self.in_tbody = True
        elif tag == 'tr':
            self.in_row = True
            self.current_row = []
        elif tag in ('td', 'th'):
            self.in_cell = True
            
    def handle_endtag(self, tag):
        if tag == 'table':
            self.in_table = False
        elif tag == 'thead':
            self.in_header = False
        elif tag == 'tbody':
            self.in_tbody = False
        elif tag == 'tr':
            self.in_row = False
            if self.in_header:
                self.headers = self.current_row
            elif self.in_tbody:
                self.rows.append(self.current_row)
        elif tag in ('td', 'th'):
            self.in_cell = False
            
    def handle_data(self, data):
        if self.in_cell and self.in_row:
            text = data.strip()
            if text:
                self.current_row.append(text)


def parse_javascript_lufs(content: str) -> dict:
    """Parse LUFS data from JavaScript format in older Reaper render_stats files.
    
    Older Reaper versions store LUFS in JavaScript like:
        integrated:['LUFS-I',0.2589,'-20.75'],
        dynrange:['LRA',[0.5649,'-38.20'],[0.1789,'-16.20']],
        truepeak:['True Peak','-0.89'],
    """
    result = {}
    
    # Extract filename from title tag
    title_match = re.search(r'<title>([^<]+)</title>', content)
    if title_match:
        result['filename'] = title_match.group(1).strip()
    
    # Extract LUFS-I (integrated loudness)
    # Format: integrated:['LUFS-I',0.2589,'-20.75']
    lufs_match = re.search(r"integrated:\s*\['LUFS-I',[\d.]+,'([-\d.]+)'\]", content)
    if lufs_match:
        result['lufs_i'] = float(lufs_match.group(1))
    
    # Extract LRA (loudness range)
    # Format: dynrange:['LRA',[0.5649,'-38.20'],[0.1789,'-16.20']]
    # The two values represent the quiet and loud ends of the range
    lra_match = re.search(r"dynrange:\s*\['LRA',\[[\d.]+,'([-\d.]+)'\],\[[\d.]+,'([-\d.]+)'\]\]", content)
    if lra_match:
        # LRA is the difference between loud and quiet
        quiet = float(lra_match.group(1))
        loud = float(lra_match.group(2))
        result['lra'] = loud - quiet
    
    # Extract True Peak
    # Format: truepeak:['True Peak','-0.89']
    tp_match = re.search(r"truepeak:\s*\['True Peak','([-\d.]+)'\]", content)
    if tp_match:
        result['true_peak_db'] = float(tp_match.group(1))
    
    # Extract duration from JavaScript
    # Format: "m:ss" or "h:mm:ss" typically in page
    dur_match = re.search(r'(\d+:\d+(?::\d+)?(?:\.\d+)?)\s*(?:</td>|<br>)', content)
    if dur_match:
        result['duration'] = dur_match.group(1)
    
    return result if result.get('lufs_i') is not None else None


def parse_render_stats_html(html_path: Path) -> dict:
    """Parse a single render_stats.html file and return metrics.
    
    Handles multiple formats:
    1. Newer Reaper: HTML table with 11 columns (includes normalization, true peak, TP clips)
    2. Older Reaper: HTML table with 8 columns (no normalization, true peak, TP clips)
    3. Oldest Reaper: JavaScript chart data with integrated/dynrange/truepeak
    """
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # First try HTML table parser
    parser = RenderStatsParser()
    parser.feed(content)
    
    if parser.rows and parser.headers:
        row = parser.rows[0]
        headers = [h.lower().replace(' ', '').replace('-', '') for h in parser.headers]
        
        # Build a mapping from our field names to indices
        def find_value(field_names, default=None):
            """Find a value by checking multiple possible header names."""
            for name in field_names:
                name_clean = name.lower().replace(' ', '').replace('-', '')
                for i, h in enumerate(headers):
                    if name_clean in h or h in name_clean:
                        if i < len(row):
                            return row[i]
            return default
        
        def parse_float(val):
            """Safely parse float, return None for '-' or invalid."""
            if val is None or val == '-':
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None
        
        def parse_int(val):
            """Safely parse int, return 0 for invalid."""
            if val is None:
                return 0
            try:
                return int(val)
            except (ValueError, TypeError):
                return 0
        
        result = {
            'filename': find_value(['file', 'filename']),
            'duration': find_value(['length', 'duration']),
            'normalization_db': parse_float(find_value(['normalized', 'adjusted', 'normalization'])),
            'peak_db': parse_float(find_value(['peak'])),
            'true_peak_db': parse_float(find_value(['truepeak', 'true peak'])),
            'clips': parse_int(find_value(['clips'])),
            'tp_clips': parse_int(find_value(['tpclips'])),
            'lufs_m_max': parse_float(find_value(['lufsm', 'maxlufsm'])),
            'lufs_s_max': parse_float(find_value(['lufss', 'maxlufss'])),
            'lufs_i': parse_float(find_value(['lufsi', 'integrated'])),
            'lra': parse_float(find_value(['lra', 'loudnessrange'])),
        }
        
        # Parse duration to seconds
        if result['duration']:
            parts = result['duration'].split(':')
            try:
                if len(parts) == 2:
                    mins, secs = parts
                    result['duration_seconds'] = int(mins) * 60 + float(secs)
                elif len(parts) == 3:
                    hrs, mins, secs = parts
                    result['duration_seconds'] = int(hrs) * 3600 + int(mins) * 60 + float(secs)
            except (ValueError, TypeError):
                result['duration_seconds'] = None
        
        # If table parsing didn't get LUFS, try JavaScript parsing as fallback
        if result.get('lufs_i') is None:
            js_result = parse_javascript_lufs(content)
            if js_result:
                result.update({k: v for k, v in js_result.items() if result.get(k) is None})
        
        return result
    
    # Fall back to JavaScript parser for older format files
    js_result = parse_javascript_lufs(content)
    if js_result:
        # Add default values for fields not in JS format
        result = {
            'filename': js_result.get('filename'),
            'duration': js_result.get('duration'),
            'duration_seconds': None,
            'normalization_db': None,
            'peak_db': None,
            'true_peak_db': js_result.get('true_peak_db'),
            'clips': 0,
            'tp_clips': 0,
            'lufs_m_max': None,
            'lufs_s_max': None,
            'lufs_i': js_result.get('lufs_i'),
            'lra': js_result.get('lra'),
        }
        
        # Parse duration to seconds if available
        if result['duration']:
            parts = result['duration'].split(':')
            try:
                if len(parts) == 2:
                    mins, secs = parts
                    result['duration_seconds'] = int(mins) * 60 + float(secs)
                elif len(parts) == 3:
                    hrs, mins, secs = parts
                    result['duration_seconds'] = int(hrs) * 3600 + int(mins) * 60 + float(secs)
            except ValueError:
                pass
        
        return result
    
    return None


def scan_corpus_render_stats():
    """Scan all render directories for stats files."""
    all_stats = []
    
    for session_dir in sorted(CORPUS_DIR.iterdir()):
        if not session_dir.is_dir():
            continue
        if session_dir.name.startswith('.'):
            continue
            
        render_dir = session_dir / "render"
        if not render_dir.exists():
            continue
        
        session_name = session_dir.name
        
        for html_file in sorted(render_dir.glob("*.render_stats.html")):
            # Skip macOS metadata files
            if html_file.name.startswith('._'):
                continue
                
            stats = parse_render_stats_html(html_file)
            if stats:
                stats['session'] = session_name
                stats['stats_file'] = html_file.name
                all_stats.append(stats)
    
    return all_stats


def generate_summary(stats: list) -> dict:
    """Generate summary statistics from parsed data."""
    lufs_values = [s['lufs_i'] for s in stats if s['lufs_i'] is not None]
    
    summary = {
        'total_files': len(stats),
        'files_with_lufs': len(lufs_values),
        'lufs_min': min(lufs_values) if lufs_values else None,
        'lufs_max': max(lufs_values) if lufs_values else None,
        'lufs_mean': sum(lufs_values) / len(lufs_values) if lufs_values else None,
        'anomalies': [s for s in stats if s['lufs_i'] and s['lufs_i'] < -35],
        'sessions_count': len(set(s['session'] for s in stats)),
    }
    
    return summary


def main():
    print("="*60)
    print("REAPER RENDER STATS PARSER")
    print("="*60)
    
    print("\n1. Scanning corpus for render_stats.html files...")
    stats = scan_corpus_render_stats()
    print(f"   Found {len(stats)} render stats files")
    
    # Generate summary
    summary = generate_summary(stats)
    print(f"\n2. Summary:")
    print(f"   Sessions: {summary['sessions_count']}")
    print(f"   Total files: {summary['total_files']}")
    print(f"   LUFS range: {summary['lufs_min']:.1f} to {summary['lufs_max']:.1f}")
    print(f"   LUFS mean: {summary['lufs_mean']:.1f}")
    if summary['anomalies']:
        print(f"   Anomalies (< -35 LUFS): {len(summary['anomalies'])}")
        for a in summary['anomalies']:
            print(f"     - {a['filename']}: {a['lufs_i']:.1f} LUFS")
    
    # Export to CSV
    csv_path = OUTPUT_DIR / "render_stats_all.csv"
    print(f"\n3. Exporting to {csv_path}")
    
    fieldnames = ['session', 'filename', 'duration', 'duration_seconds', 
                  'normalization_db', 'peak_db', 'true_peak_db', 
                  'clips', 'tp_clips', 'lufs_m_max', 'lufs_s_max', 
                  'lufs_i', 'lra', 'stats_file']
    
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for s in stats:
            row = {k: s.get(k) for k in fieldnames}
            writer.writerow(row)
    
    # Export to YAML (grouped by session)
    yaml_path = OUTPUT_DIR / "render_stats_all.yaml"
    print(f"   Exporting to {yaml_path}")
    
    by_session = {}
    for s in stats:
        session = s['session']
        if session not in by_session:
            by_session[session] = []
        by_session[session].append({
            'filename': s['filename'],
            'lufs_i': s['lufs_i'],
            'true_peak_db': s['true_peak_db'],
            'duration': s['duration'],
            'lra': s['lra'],
        })
    
    yaml_data = {
        'generated': datetime.now().isoformat(),
        'total_files': len(stats),
        'sessions': by_session,
    }
    
    with open(yaml_path, 'w') as f:
        yaml.dump(yaml_data, f, default_flow_style=False, allow_unicode=True)
    
    print("\n" + "="*60)
    print("DONE")
    print("="*60)
    
    return stats


if __name__ == "__main__":
    main()
