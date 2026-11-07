#!/usr/bin/env python3
"""Generate project stats from a git checkout (stdlib only, no API token).

    python3 tools/stats.py --src path/to/checkout --out . --name HASE-HGV/Roboterarm-Hase

Writes stats.json, summary.svg and languages.svg into --out.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape

LANG_BY_EXT = {
    ".rs": "Rust", ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".html": "HTML", ".css": "CSS", ".scad": "OpenSCAD", ".c": "C", ".h": "C",
    ".cpp": "C++", ".ino": "C++", ".sh": "Shell", ".cmd": "Batch",
    ".yml": "YAML", ".yaml": "YAML", ".toml": "TOML",
}
LANG_COLORS = {
    "Rust": "#dea584", "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#3178c6",
    "HTML": "#e34c26", "CSS": "#563d7c", "OpenSCAD": "#e5cd45", "C": "#555555", "C++": "#f34b7d",
    "Shell": "#89e051", "Batch": "#C1F12E", "YAML": "#cb171e", "TOML": "#9c4221",
}
FONT = "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif"


def git(src: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(src), *args], check=True,
                          capture_output=True, text=True).stdout


def collect_commits(src: Path) -> list[dict]:
    out = git(src, "log", "--format=%an%x1f%aI%x1e", "HEAD")
    commits = []
    for record in out.split("\x1e"):
        record = record.strip()
        if record:
            name, date = record.split("\x1f")
            commits.append({"author": name, "date": dt.datetime.fromisoformat(date)})
    return commits


def collect_languages(src: Path) -> dict[str, int]:
    totals: Counter[str] = Counter()
    for path in git(src, "ls-files", "-z").split("\0"):
        lang = LANG_BY_EXT.get(Path(path).suffix.lower())
        full = src / path
        if path and lang and full.is_file():
            totals[lang] += full.stat().st_size
    return dict(totals.most_common())


def build_stats(name: str, commits: list[dict], languages: dict[str, int]) -> dict:
    newest = max(c["date"] for c in commits)
    oldest = min(c["date"] for c in commits)
    per_author = Counter(c["author"] for c in commits)
    total = sum(languages.values()) or 1
    return {
        "repo": name,
        # Newest commit date, so the output only changes when the history does.
        "generated_at": newest.isoformat(),
        "commits": len(commits),
        "contributors": len(per_author),
        "active_days": len({c["date"].date() for c in commits}),
        "first_commit": oldest.date().isoformat(),
        "last_commit": newest.date().isoformat(),
        "top_contributors": [{"name": n, "commits": c} for n, c in per_author.most_common(10)],
        "languages": [{"name": n, "bytes": b, "percent": round(100 * b / total, 1)}
                      for n, b in languages.items()],
    }


def summary_svg(stats: dict) -> str:
    items = [("Commits", str(stats["commits"])), ("Contributors", str(stats["contributors"])),
             ("Active days", str(stats["active_days"])), ("Last commit", stats["last_commit"])]
    width, height = 620, 110
    col = width / len(items)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="Project stats">',
        f'<rect width="{width}" height="{height}" rx="12" fill="#0d1117" stroke="#30363d"/>',
        f'<text x="20" y="28" fill="#8b949e" font-family="{FONT}" font-size="13">'
        f'Roboterarm HASE · git statistics</text>',
    ]
    for i, (label, value) in enumerate(items):
        x = col * i + 20
        parts.append(f'<text x="{x:.0f}" y="66" fill="#58a6ff" font-family="{FONT}" '
                     f'font-size="24" font-weight="700">{escape(value)}</text>')
        parts.append(f'<text x="{x:.0f}" y="88" fill="#8b949e" font-family="{FONT}" '
                     f'font-size="12">{escape(label)}</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def languages_svg(stats: dict) -> str:
    langs = stats["languages"][:8]
    width, bar_y, bar_h, row_h = 620, 36, 14, 22
    usable = width - 40
    height = 62 + row_h * ((len(langs) + 1) // 2) + 10
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="Languages">',
        f'<rect width="{width}" height="{height}" rx="12" fill="#0d1117" stroke="#30363d"/>',
        f'<text x="20" y="24" fill="#8b949e" font-family="{FONT}" font-size="13">'
        f'Languages (tracked source files)</text>',
    ]
    x = 20.0
    for lang in langs:
        w = usable * lang["percent"] / 100
        color = LANG_COLORS.get(lang["name"], "#8b949e")
        parts.append(f'<rect x="{x:.1f}" y="{bar_y}" width="{max(w, 1):.1f}" height="{bar_h}" fill="{color}"/>')
        x += w
    for i, lang in enumerate(langs):
        col_x = 20 + (i % 2) * (usable / 2)
        row_y = bar_y + bar_h + 24 + (i // 2) * row_h
        color = LANG_COLORS.get(lang["name"], "#8b949e")
        parts.append(f'<circle cx="{col_x + 5:.0f}" cy="{row_y - 4}" r="5" fill="{color}"/>')
        parts.append(f'<text x="{col_x + 16:.0f}" y="{row_y}" fill="#c9d1d9" font-family="{FONT}" '
                     f'font-size="13">{escape(lang["name"])} '
                     f'<tspan fill="#8b949e">{lang["percent"]:.1f} %</tspan></text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--src", required=True, help="path to the git checkout to analyse")
    p.add_argument("--out", default=".", help="directory to write stats.json and the SVGs into")
    p.add_argument("--name", required=True, help="owner/repo, recorded in stats.json")
    a = p.parse_args()

    src, out = Path(a.src).resolve(), Path(a.out)
    commits = collect_commits(src)
    if not commits:
        raise SystemExit("no commits found")
    stats = build_stats(a.name, commits, collect_languages(src))
    out.mkdir(parents=True, exist_ok=True)
    (out / "stats.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "summary.svg").write_text(summary_svg(stats), encoding="utf-8")
    (out / "languages.svg").write_text(languages_svg(stats), encoding="utf-8")
    print(f"{a.name}: {len(commits)} commits, {stats['contributors']} contributors -> {out}")


if __name__ == "__main__":
    main()
