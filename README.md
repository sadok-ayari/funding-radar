# funding-radar

Turn funding sources into a screened, de-duplicated digest — from the command line, with no model in the loop.

Point it at the feeds and APIs your sector actually uses. It fetches, normalises, collapses duplicates, scores each call against a profile you control, and writes a Markdown digest plus a JSON record. Every score is a list of rules you can read and argue with.

```
$ funding-radar run --now 2026-11-12
2026-11-12: 26 new of 26 scored (1 pursue, 1 watch)
digest: out/digest.md
```

## Why

The expensive part of opportunity tracking is not finding calls, it is deciding which ones are worth a proposal — and doing it before the deadline, not after. In most teams that judgement lives in one person's head, so it is neither auditable nor repeatable, and calls surface late because nobody is watching every funder every week.

This tool makes the judgement explicit. A profile lists the themes, the value band, the geography and the deadline window. The screen applies them in a fixed order and prints the reason for every point awarded or withheld. If you disagree with an outcome, you change one line of the profile — not a prompt, and not a model.

## Install

Python 3.9 or later. Nothing else.

```bash
git clone https://github.com/sadok-ayari/funding-radar.git
cd funding-radar
python -m radar run           # writes out/digest.md
```

Optionally install the command:

```bash
pip install -e .
funding-radar run
```

## Output

`out/digest.md` — the readable brief, grouped into **Pursue**, **Watch** and **Not a fit**, ending with any sources that failed. `out/items.json` — the same run as data, one object per call, including its score and reasons. See [examples/example-digest.md](examples/example-digest.md) for a real run.

## Configuration

Two files, both plain JSON, no code.

`config/profile.json` — what counts as a fit:

| Key | Meaning |
|---|---|
| `rules.themes` | keywords that make a call relevant |
| `rules.require_theme` | `true` means no theme match is an automatic exclusion |
| `rules.countries` | allow-list; empty means no geographic restriction |
| `rules.exclude_keywords` | terms that disqualify a call outright |
| `rules.min_amount` / `max_amount` | the value band you can actually absorb |
| `rules.deadline_window_days` | how far ahead is useful |
| `weights` | points per component; `theme` is worth the most |
| `thresholds` | score cut-offs for `pursue` and `watch` |

`config/sources.json` — where calls come from. Each entry declares a `type`:

| Type | For | Needs |
|---|---|---|
| `rss` | any RSS or Atom feed | `url` |
| `ted` | the EU Tenders Electronic Daily API | `url`, optional `query`, optional `cpv_prefixes` |
| `html_list` | a plain page of links, last resort | `url`, `link_pattern` with named groups `href` and `text` |

`tier` (1–3) expresses how authoritative the source is; it carries points, so a funder's own page outranks an aggregator.

## Reproducibility

- `--now YYYY-MM-DD` fixes the clock, so a screening decision can be replayed.
- `--offline` replays the last cached payloads; `--cache DIR` says where they live.
- `--dry-run` writes nothing to the seen-list; `--include-seen` ignores it for one run.
- The seen-list is SQLite (`radar.db`), so the same call does not reappear next week.

## Extending

Adding a funder is a block in `config/sources.json`. Write a new adapter in `radar/adapters.py` only when a source has neither a feed nor an API; the base class handles date, deadline and amount extraction for you. Tests use fixture payloads and never touch the network, so a broken selector shows up in CI rather than in a digest.

```bash
python -m unittest discover -s tests      # 38 tests, stdlib only
```

## Deliberate limits

- No summaries, no model calls: titles and snippets are passed through as published. Nothing is invented.
- A source that fails is reported at the top of the digest and in the run record. It is never silently dropped.
- `not stated` means the listing did not state it. Verify the deadline and the amount at source before you plan work.
- Procurement notices (`ted`) are not grants. The `cpv_prefixes` filter is there to cut unrelated goods and services; keep it tuned or disable the source.

## Licence

MIT — see [LICENSE](LICENSE).
