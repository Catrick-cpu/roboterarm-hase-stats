#!/usr/bin/env python3
"""Generate project statistics and SVG charts from a git checkout.

    python3 tools/stats.py --src path/to/checkout --out . --name HASE-HGV/Roboterarm-Hase

Git-derived outputs (always written):
    stats.json, summary.svg, languages.svg, heatmap.svg, weekday_hour.svg,
    commits_per_month.svg, cumulative_commits.svg, contributors.svg,
    timeline.svg, hotspots.svg, loc_over_time.svg, languages_over_time.svg,
    tests_over_time.svg, repo_size.svg

API-derived outputs (written only when SOURCE_TOKEN is set):
    ci.svg, issues.svg

Standard library only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import statistics
import subprocess
import urllib.request
from collections import Counter, defaultdict
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
GREENS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
FONT = "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
BG, FG, MUTED, BORDER = "#0d1117", "#c9d1d9", "#8b949e", "#30363d"
BLUE, GREEN, ORANGE, PURPLE = "#58a6ff", "#3fb950", "#d29922", "#bc8cff"
WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
MONTHS_DE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
SOURCE_REPO = "HASE-HGV/Roboterarm-Hase"
CI_WORKFLOW = "rust.yml"


# --------------------------------------------------------------------------- git

def git(src: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(src), *args], check=True,
                          capture_output=True, text=True).stdout


def collect_commits(src: Path) -> list[dict]:
    """Newest first. Each: sha, author, date (aware datetime)."""
    out = git(src, "log", "--format=%H%x1f%an%x1f%aI%x1e", "HEAD")
    commits = []
    for record in out.split("\x1e"):
        record = record.strip()
        if record:
            sha, name, date = record.split("\x1f")
            commits.append({"sha": sha, "author": name, "date": dt.datetime.fromisoformat(date)})
    return commits


def collect_numstat(src: Path) -> dict[str, dict]:
    """Per commit sha: added/deleted line counts (binary files count as 0)."""
    out = git(src, "log", "--numstat", "--format=%x1e%H")
    result: dict[str, dict] = {}
    for record in out.split("\x1e"):
        lines = [l for l in record.splitlines() if l.strip()]
        if not lines:
            continue
        added = deleted = 0
        for l in lines[1:]:
            parts = l.split("\t")
            if len(parts) == 3:
                added += int(parts[0]) if parts[0].isdigit() else 0
                deleted += int(parts[1]) if parts[1].isdigit() else 0
        result[lines[0].strip()] = {"added": added, "deleted": deleted}
    return result


def collect_hotspots(src: Path, top: int = 15) -> list[tuple[str, int]]:
    out = git(src, "log", "--name-only", "--format=")
    counts = Counter(l.strip() for l in out.splitlines() if l.strip())
    return counts.most_common(top)


def month_snapshots(commits: list[dict]) -> list[tuple[str, str]]:
    """(label 'YYYY-MM', sha) of the last commit of each month, oldest first."""
    ordered = sorted(commits, key=lambda c: c["date"])
    last_in_month: dict[str, str] = {}
    for c in ordered:
        last_in_month[c["date"].strftime("%Y-%m")] = c["sha"]
    return sorted(last_in_month.items())


def snapshot_metrics(src: Path, sha: str) -> dict:
    """Source lines, tracked bytes and #[test] count at one commit."""
    lang_bytes: Counter[str] = Counter()
    total_bytes = 0
    for line in git(src, "ls-tree", "-r", "-l", sha).splitlines():
        meta, path = line.split("\t", 1)
        size = meta.split()[3]
        if size.isdigit():
            total_bytes += int(size)
            lang = LANG_BY_EXT.get(Path(path).suffix.lower())
            if lang:
                lang_bytes[lang] += int(size)

    exts = sorted({f"*{e}" for e in LANG_BY_EXT})
    lang_lines: Counter[str] = Counter()
    grep = subprocess.run(["git", "-C", str(src), "grep", "-c", "", sha, "--", *exts],
                          capture_output=True, text=True)
    for line in grep.stdout.splitlines():
        _, path, count = line.split(":", 2)
        lang = LANG_BY_EXT.get(Path(path).suffix.lower())
        if lang:
            lang_lines[lang] += int(count)

    tests = 0
    tgrep = subprocess.run(["git", "-C", str(src), "grep", "-c", "-F", "#[test]", sha, "--", "*.rs"],
                           capture_output=True, text=True)
    for line in tgrep.stdout.splitlines():
        tests += int(line.rsplit(":", 1)[1])

    return {
        "bytes": total_bytes,
        "loc_by_lang": dict(lang_lines),
        "loc": sum(lang_lines.values()),
        "tests": tests,
    }


def languages_now(src: Path) -> dict[str, int]:
    totals: Counter[str] = Counter()
    for path in git(src, "ls-files", "-z").split("\0"):
        lang = LANG_BY_EXT.get(Path(path).suffix.lower())
        full = src / path
        if path and lang and full.is_file():
            totals[lang] += full.stat().st_size
    return dict(totals.most_common())


# --------------------------------------------------------------------------- api

def gh_get(path: str, token: str):
    req = urllib.request.Request(
        "https://api.github.com" + path,
        headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
                 "X-GitHub-Api-Version": "2022-11-28"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def gh_paginate(path: str, token: str, pages: int = 3) -> list:
    items: list = []
    for page in range(1, pages + 1):
        sep = "&" if "?" in path else "?"
        batch = gh_get(f"{path}{sep}per_page=100&page={page}", token)
        items.extend(batch)
        if len(batch) < 100:
            break
    return items


def fetch_ci(token: str) -> dict | None:
    runs = gh_get(f"/repos/{SOURCE_REPO}/actions/workflows/{CI_WORKFLOW}/runs?branch=main&per_page=1", token)
    if not runs.get("workflow_runs"):
        return None
    r = runs["workflow_runs"][0]
    return {"conclusion": r["conclusion"] or r["status"], "at": r["created_at"][:10]}


def _parse_ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def fetch_issues(token: str) -> dict:
    items = gh_paginate(f"/repos/{SOURCE_REPO}/issues?state=all", token)
    issues = [i for i in items if "pull_request" not in i]
    pulls = gh_paginate(f"/repos/{SOURCE_REPO}/pulls?state=all", token)
    merged = [p for p in pulls if p.get("merged_at")]
    durations = [(_parse_ts(p["merged_at"]) - _parse_ts(p["created_at"])).total_seconds() / 86400
                 for p in merged]
    return {
        "open_issues": sum(1 for i in issues if i["state"] == "open"),
        "closed_issues": sum(1 for i in issues if i["state"] == "closed"),
        "open_prs": sum(1 for p in pulls if p["state"] == "open"),
        "merged_prs": len(merged),
        "median_days_to_merge": round(statistics.median(durations), 1) if durations else None,
    }


# --------------------------------------------------------------------------- svg

class Svg:
    def __init__(self, width: int, height: int, title: str):
        self.w, self.h = width, height
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">',
            f'<rect width="{width}" height="{height}" rx="12" fill="{BG}" stroke="{BORDER}"/>',
            f'<text x="20" y="26" fill="{MUTED}" font-family="{FONT}" font-size="13">{escape(title)}</text>',
        ]

    def add(self, s: str) -> None:
        self.parts.append(s)

    def text(self, x, y, s, fill=FG, size=11, anchor="start", weight="400") -> None:
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" font-family="{FONT}" '
                 f'font-size="{size}" text-anchor="{anchor}" font-weight="{weight}">{escape(str(s))}</text>')

    def rect(self, x, y, w, h, fill, rx=0, title=None) -> None:
        t = f"<title>{escape(title)}</title>" if title else ""
        self.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w, 0):.1f}" height="{max(h, 0):.1f}" '
                 f'rx="{rx}" fill="{fill}">{t}</rect>')

    def render(self) -> str:
        return "\n".join(self.parts + ["</svg>"]) + "\n"


def level(value: float, maximum: float) -> int:
    if value <= 0 or maximum <= 0:
        return 0
    return min(4, max(1, math.ceil(value / maximum * 4)))


def legend(svg: Svg, items: list[tuple[str, str]]) -> None:
    lx = 20
    for name, color in items:
        svg.rect(lx, svg.h - 16, 10, 10, color, rx=2)
        svg.text(lx + 14, svg.h - 7, name, fill=MUTED, size=10)
        lx += 14 + 7 * len(name) + 18


def heatmap_svg(title: str, matrix: list[list[float]], row_labels: list[str],
                col_labels: list[str | None], cell: int = 12, gap: int = 3) -> str:
    left, top = 44, 40
    rows, cols = len(matrix), len(matrix[0])
    width = left + cols * (cell + gap) + 20
    height = top + rows * (cell + gap) + 16
    svg = Svg(width, height, title)
    maximum = max((v for r in matrix for v in r), default=0)
    for r, label in enumerate(row_labels):
        svg.text(8, top + r * (cell + gap) + cell - 2, label, fill=MUTED, size=10)
        for c in range(cols):
            v = matrix[r][c]
            svg.rect(left + c * (cell + gap), top + r * (cell + gap), cell, cell,
                     GREENS[level(v, maximum)], rx=2, title=f"{v:g}")
    for c, label in enumerate(col_labels):
        if label:
            svg.text(left + c * (cell + gap), top - 8, label, fill=MUTED, size=10)
    return svg.render()


def bar_chart_svg(title: str, labels: list[str], series: list[tuple[str, str, list[float]]],
                  width: int = 620, height: int = 240) -> str:
    left, right, top, bottom = 44, 16, 44, 40
    plot_w, plot_h = width - left - right, height - top - bottom
    totals = [sum(s[2][i] for s in series) for i in range(len(labels))]
    maximum = max(totals, default=1) or 1
    svg = Svg(width, height, title)
    slot = plot_w / max(len(labels), 1)
    bar_w = slot * 0.7
    every = max(1, len(labels) // 12)
    for i, label in enumerate(labels):
        x = left + i * slot + (slot - bar_w) / 2
        y = top + plot_h
        for name, color, values in series:
            h = plot_h * values[i] / maximum
            y -= h
            svg.rect(x, y, bar_w, h, color, title=f"{label}: {values[i]:g} {name}")
        if i % every == 0:
            svg.text(x + bar_w / 2, top + plot_h + 14, label, fill=MUTED, size=9, anchor="middle")
    svg.text(left - 6, top + 4, f"{maximum:g}", fill=MUTED, size=9, anchor="end")
    svg.text(left - 6, top + plot_h, "0", fill=MUTED, size=9, anchor="end")
    if len(series) > 1:
        legend(svg, [(name, color) for name, color, _ in series])
    return svg.render()


def line_chart_svg(title: str, labels: list[str], series: list[tuple[str, str, list[float]]],
                   width: int = 620, height: int = 240) -> str:
    left, right, top, bottom = 52, 16, 44, 40
    plot_w, plot_h = width - left - right, height - top - bottom
    maximum = max((max(s[2]) for s in series if s[2]), default=1) or 1
    svg = Svg(width, height, title)
    n = len(labels)
    step = plot_w / max(n - 1, 1)
    for name, color, values in series:
        pts = [(left + i * step, top + plot_h - plot_h * v / maximum) for i, v in enumerate(values)]
        if len(pts) > 1:
            poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
            area = f"{left:.1f},{top + plot_h:.1f} {poly} {pts[-1][0]:.1f},{top + plot_h:.1f}"
            svg.add(f'<polygon points="{area}" fill="{color}" fill-opacity="0.12"/>')
            svg.add(f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2"/>')
        for (x, y), v, lab in zip(pts, values, labels):
            svg.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="{color}">'
                    f'<title>{escape(lab)}: {v:g} {escape(name)}</title></circle>')
    svg.text(left - 6, top + 4, f"{maximum:g}", fill=MUTED, size=9, anchor="end")
    svg.text(left - 6, top + plot_h, "0", fill=MUTED, size=9, anchor="end")
    every = max(1, n // 8)
    for i, lab in enumerate(labels):
        if i % every == 0 or i == n - 1:
            svg.text(left + i * step, top + plot_h + 14, lab, fill=MUTED, size=9, anchor="middle")
    if len(series) > 1:
        legend(svg, [(name, color) for name, color, _ in series])
    return svg.render()


def hbar_svg(title: str, rows: list[tuple[str, float, str]], color: str = BLUE,
             width: int = 620, row_h: int = 24) -> str:
    left, top = 170, 40
    height = top + row_h * len(rows) + 16
    maximum = max((v for _, v, _ in rows), default=1) or 1
    svg = Svg(width, height, title)
    bar_max = width - left - 150
    for i, (label, value, note) in enumerate(rows):
        y = top + i * row_h
        w = bar_max * value / maximum
        svg.text(left - 10, y + 15, label, anchor="end", size=12)
        svg.rect(left, y + 4, w, row_h - 10, color, rx=3, title=f"{label}: {value:g}")
        svg.text(left + w + 8, y + 15, f"{value:g}{note}", fill=MUTED, size=11)
    return svg.render()


def card_svg(title: str, items: list[tuple[str, str]], width: int = 620) -> str:
    col = (width - 40) / max(len(items), 1)
    svg = Svg(width, 110, title)
    for i, (label, value) in enumerate(items):
        x = 20 + col * i
        svg.text(x, 66, value, fill=BLUE, size=24, weight="700")
        svg.text(x, 88, label, fill=MUTED, size=12)
    return svg.render()


def languages_card(langs: list[dict]) -> str:
    shown = langs[:8]
    width, bar_y, bar_h, row_h = 620, 36, 14, 22
    usable = width - 40
    height = 62 + row_h * ((len(shown) + 1) // 2) + 10
    svg = Svg(width, height, "Languages (tracked source files)")
    x = 20.0
    for lang in shown:
        w = usable * lang["percent"] / 100
        svg.rect(x, bar_y, max(w, 1), bar_h, LANG_COLORS.get(lang["name"], MUTED))
        x += w
    for i, lang in enumerate(shown):
        cx = 20 + (i % 2) * (usable / 2)
        ry = bar_y + bar_h + 24 + (i // 2) * row_h
        svg.add(f'<circle cx="{cx + 5:.0f}" cy="{ry - 4}" r="5" fill="{LANG_COLORS.get(lang["name"], MUTED)}"/>')
        svg.text(cx + 16, ry, f'{lang["name"]}  {lang["percent"]:.1f} %', size=13)
    return svg.render()


def summary_card(stats: dict) -> str:
    return card_svg("Roboterarm HASE · git statistics", [
        ("Commits", str(stats["commits"])),
        ("Contributors", str(stats["contributors"])),
        ("Active days", str(stats["active_days"])),
        ("Last commit", stats["last_commit"]),
    ])


# --------------------------------------------------------------------------- build

def build(args) -> dict[str, str]:
    src = Path(args.src).resolve()
    commits = collect_commits(src)
    if not commits:
        raise SystemExit("no commits found")
    numstat = collect_numstat(src)
    now_langs = languages_now(src)
    total_now = sum(now_langs.values()) or 1
    per_author: Counter[str] = Counter(c["author"] for c in commits)
    newest = max(c["date"] for c in commits)
    oldest = min(c["date"] for c in commits)

    stats: dict = {
        "repo": args.name,
        "generated_at": newest.isoformat(),  # newest commit: output only changes with history
        "commits": len(commits),
        "contributors": len(per_author),
        "active_days": len({c["date"].date() for c in commits}),
        "first_commit": oldest.date().isoformat(),
        "last_commit": newest.date().isoformat(),
        "top_contributors": [{"name": n, "commits": c} for n, c in per_author.most_common(10)],
        "languages": [{"name": n, "bytes": b, "percent": round(100 * b / total_now, 1)}
                      for n, b in now_langs.items()],
    }
    charts: dict[str, str] = {
        "summary.svg": summary_card(stats),
        "languages.svg": languages_card(stats["languages"]),
    }

    # Calendar heatmap: 53 Monday-aligned weeks ending with the newest commit's week.
    today = newest.date()
    start = today - dt.timedelta(days=today.weekday()) - dt.timedelta(weeks=52)
    per_day = Counter(c["date"].date() for c in commits)
    matrix = [[0.0] * 53 for _ in range(7)]
    col_labels: list[str | None] = [None] * 53
    for w in range(53):
        week_start = start + dt.timedelta(weeks=w)
        if week_start.day <= 7:
            col_labels[w] = MONTHS_DE[week_start.month - 1]
        for d in range(7):
            day = week_start + dt.timedelta(days=d)
            if day <= today:
                matrix[d][w] = per_day.get(day, 0)
    charts["heatmap.svg"] = heatmap_svg("Commits per day (last year)", matrix, WEEKDAYS, col_labels)
    stats["commits_last_year"] = int(sum(sum(r) for r in matrix))

    wh = [[0.0] * 24 for _ in range(7)]
    for c in commits:
        wh[c["date"].weekday()][c["date"].hour] += 1
    charts["weekday_hour.svg"] = heatmap_svg(
        "Commits by weekday and hour (author local time)", wh, WEEKDAYS,
        [str(h) if h % 3 == 0 else None for h in range(24)])

    # Per month: commits, cumulative commits
    per_month = Counter(c["date"].strftime("%Y-%m") for c in commits)
    months: list[str] = []
    cursor = dt.date(oldest.year, oldest.month, 1)
    while cursor <= today:
        months.append(cursor.strftime("%Y-%m"))
        cursor = (cursor.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    month_labels = [f"{m[5:]}.{m[2:4]}" for m in months]
    counts = [float(per_month.get(m, 0)) for m in months]
    charts["commits_per_month.svg"] = bar_chart_svg(
        "Commits per month", month_labels, [("commits", BLUE, counts)])
    running, cumulative = 0.0, []
    for v in counts:
        running += v
        cumulative.append(running)
    charts["cumulative_commits.svg"] = line_chart_svg(
        "Cumulative commits", month_labels, [("commits", GREEN, cumulative)])

    # Contributors: commits and lines changed
    lines_by_author: Counter[str] = Counter()
    weeks_by_author: dict[str, set] = defaultdict(set)
    for c in commits:
        ns = numstat.get(c["sha"], {"added": 0, "deleted": 0})
        lines_by_author[c["author"]] += ns["added"] + ns["deleted"]
        weeks_by_author[c["author"]].add(c["date"].isocalendar()[:2])
    top_people = [n for n, _ in per_author.most_common(10)]
    charts["contributors.svg"] = hbar_svg(
        "Commits per contributor",
        [(n, per_author[n], f"  ·  {lines_by_author[n]:,} lines".replace(",", ".")) for n in top_people],
        color=PURPLE, row_h=26)

    # Timeline: commits per week per contributor over the last year
    week_starts = [start + dt.timedelta(weeks=w) for w in range(53)]
    week_keys = [ws.isocalendar()[:2] for ws in week_starts]
    tl = [[0.0] * 53 for _ in top_people]
    for c in commits:
        key = c["date"].isocalendar()[:2]
        if key in week_keys and c["author"] in top_people:
            tl[top_people.index(c["author"])][week_keys.index(key)] += 1
    charts["timeline.svg"] = heatmap_svg(
        "Activity per contributor (weekly, last year)", tl, top_people,
        [MONTHS_DE[ws.month - 1] if ws.day <= 7 else None for ws in week_starts])

    hot = collect_hotspots(src)
    charts["hotspots.svg"] = hbar_svg(
        "Most changed files (commits touching the file)",
        [(Path(p).name, n, "") for p, n in hot], color=ORANGE, row_h=22)

    # Monthly snapshots: source lines, languages, tests, repo size
    snaps = month_snapshots(commits)
    snap_labels: list[str] = []
    locs: list[float] = []
    tests: list[float] = []
    sizes: list[float] = []
    lang_series: dict[str, list[float]] = defaultdict(list)
    for label, sha in snaps:
        m = snapshot_metrics(src, sha)
        snap_labels.append(f"{label[5:]}.{label[2:4]}")
        locs.append(float(m["loc"]))
        tests.append(float(m["tests"]))
        sizes.append(m["bytes"] / 1024)
        for lang in LANG_COLORS:
            lang_series[lang].append(float(m["loc_by_lang"].get(lang, 0)))
    charts["loc_over_time.svg"] = line_chart_svg(
        "Source lines of code (month end, tracked files)", snap_labels, [("lines", GREEN, locs)])
    charts["tests_over_time.svg"] = line_chart_svg(
        "Rust #[test] functions (month end)", snap_labels, [("tests", ORANGE, tests)])
    charts["repo_size.svg"] = line_chart_svg(
        "Tracked repository size (KiB, month end)", snap_labels, [("KiB", BLUE, sizes)])
    stacked = [(lang, LANG_COLORS[lang], vals) for lang, vals in lang_series.items() if any(vals)]
    charts["languages_over_time.svg"] = bar_chart_svg(
        "Source lines by language (month end)", snap_labels, stacked, height=260)
    stats["loc_now"] = int(locs[-1]) if locs else 0
    stats["tests_now"] = int(tests[-1]) if tests else 0

    # API-backed cards
    token = os.environ.get("SOURCE_TOKEN", "")
    if token:
        ci = fetch_ci(token)
        if ci:
            stats["ci"] = ci
            charts["ci.svg"] = card_svg("CI · Rust build & test on main", [
                ("Latest run", ci["conclusion"]), ("Date", ci["at"])])
        issues = fetch_issues(token)
        stats["issues"] = issues
        median = issues["median_days_to_merge"]
        charts["issues.svg"] = card_svg("Issues & pull requests", [
            ("Open issues", str(issues["open_issues"])),
            ("Closed issues", str(issues["closed_issues"])),
            ("Open PRs", str(issues["open_prs"])),
            ("Merged PRs", str(issues["merged_prs"])),
            ("Median days to merge", "–" if median is None else f"{median:g}"),
        ])

    charts["stats.json"] = json.dumps(stats, indent=2, ensure_ascii=False) + "\n"
    return charts


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--src", required=True)
    p.add_argument("--out", default=".")
    p.add_argument("--name", required=True)
    args = p.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    outputs = build(args)
    for name, content in outputs.items():
        (out / name).write_text(content, encoding="utf-8")
    print(f"wrote {len(outputs)} files -> {out}")


if __name__ == "__main__":
    main()
