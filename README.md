# roboterarm-hase-stats

Generated statistics and charts for [HASE-HGV/Roboterarm-Hase](https://github.com/HASE-HGV/Roboterarm-Hase), served as plain files so the project README can embed them. There is no website and nothing to deploy.

A scheduled workflow regenerates everything daily from the original repository's git history. The CI and issue/PR cards need the `SOURCE_TOKEN` repository secret and are skipped without it.

## Endpoints

Base URL: `https://raw.githubusercontent.com/Catrick-cpu/roboterarm-hase-stats/main/`

| File | Chart | Content |
|------|-------|---------|
| [`summary.svg`](https://raw.githubusercontent.com/Catrick-cpu/roboterarm-hase-stats/main/summary.svg) | Stats card | Commits, contributors, active days, last commit |
| [`languages.svg`](https://raw.githubusercontent.com/Catrick-cpu/roboterarm-hase-stats/main/languages.svg) | Languages | Language share of tracked source files |
| [`heatmap.svg`](https://raw.githubusercontent.com/Catrick-cpu/roboterarm-hase-stats/main/heatmap.svg) | Commit calendar | Commits per day over the last year |
| [`commits_per_month.svg`](https://raw.githubusercontent.com/Catrick-cpu/roboterarm-hase-stats/main/commits_per_month.svg) | Commits per month | Commits in each calendar month |
| [`cumulative_commits.svg`](https://raw.githubusercontent.com/Catrick-cpu/roboterarm-hase-stats/main/cumulative_commits.svg) | Cumulative commits | Running total of commits |
| [`weekday_hour.svg`](https://raw.githubusercontent.com/Catrick-cpu/roboterarm-hase-stats/main/weekday_hour.svg) | Weekday × hour | When the team commits (author local time) |
| [`contributors.svg`](https://raw.githubusercontent.com/Catrick-cpu/roboterarm-hase-stats/main/contributors.svg) | Contributors | Commits per contributor |
| [`timeline.svg`](https://raw.githubusercontent.com/Catrick-cpu/roboterarm-hase-stats/main/timeline.svg) | Contributor timeline | Weekly activity per contributor, last year |
| [`hotspots.svg`](https://raw.githubusercontent.com/Catrick-cpu/roboterarm-hase-stats/main/hotspots.svg) | Hotspot files | Files changed in the most commits |
| [`loc_over_time.svg`](https://raw.githubusercontent.com/Catrick-cpu/roboterarm-hase-stats/main/loc_over_time.svg) | Source lines | Lines in tracked source files, month end |
| [`languages_over_time.svg`](https://raw.githubusercontent.com/Catrick-cpu/roboterarm-hase-stats/main/languages_over_time.svg) | Languages over time | Source lines by language, month end |
| [`tests_over_time.svg`](https://raw.githubusercontent.com/Catrick-cpu/roboterarm-hase-stats/main/tests_over_time.svg) | Tests over time | Rust #[test] functions, month end |
| [`repo_size.svg`](https://raw.githubusercontent.com/Catrick-cpu/roboterarm-hase-stats/main/repo_size.svg) | Repository size | Tracked bytes, month end |
| [`ci.svg`](https://raw.githubusercontent.com/Catrick-cpu/roboterarm-hase-stats/main/ci.svg) | CI status | Latest run of the Rust workflow on main (needs SOURCE_TOKEN) |
| [`issues.svg`](https://raw.githubusercontent.com/Catrick-cpu/roboterarm-hase-stats/main/issues.svg) | Issues & PRs | Open/closed issues, PRs, median time to merge (needs SOURCE_TOKEN) |
| [`stats.json`](https://raw.githubusercontent.com/Catrick-cpu/roboterarm-hase-stats/main/stats.json) | Raw data | All numbers behind the charts |

## Embed in a README

```markdown
![Stats](https://raw.githubusercontent.com/Catrick-cpu/roboterarm-hase-stats/main/summary.svg)
```

## Regenerate locally

```bash
git clone https://github.com/HASE-HGV/Roboterarm-Hase.git source
python3 tools/stats.py --src source --out . --name HASE-HGV/Roboterarm-Hase
```

The git-derived charts need only the standard library. The CI and issue charts also need `SOURCE_TOKEN` set to a token that can read the repository.
