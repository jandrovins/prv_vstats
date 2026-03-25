# prv-vstats

Statistical analysis tool for Paraver traces. Reconstructs task execution intervals from `.prv`/`.pcf`/`.row` files and produces per-thread/global duration statistics, visualizations, and an LLM-friendly text export.

## Requirements

- Python 3.8+
- numpy, pandas, matplotlib

```
pip install -r requirements.txt
```

## Usage

```
python prvvstats.py <trace.prv> [--event-type N] [--filter-at-parse] [--output FILE] [--llm-output FILE]
```

| Argument | Default | Description |
|---|---|---|
| `trace.prv` | *(required)* | Path to the Paraver trace file |
| `--event-type N` | `11` | Event type ID to analyse (see PCF for IDs) |
| `--filter-at-parse` | off | Ignore non-selected event types while reading `.prv` (opt-in speed/memory mode) |
| `--output FILE` | `stats.png` | Output figure path |
| `--llm-output FILE` | — | Write LLM text export to FILE (`-` for stdout) |

The `.pcf` and `.row` files are resolved automatically from the same directory and stem as the `.prv` file.

## Output

**Stdout** — two statistics tables (global + per-thread):
`task | mean_ms | median_ms | p25_ms | p75_ms | count | pct_timeline`

**Figure** (`--output`) — violin plots per task type (top) + stacked per-thread bar chart (bottom).

**LLM export** (`--llm-output`) — structured plain-text document: task legend, stats tables, and per-thread exact interval sequences (`ABBREV@start_ms(dur_ms)`). Lossless for traces under ~5 seconds.

## Event types (OVNI/nOS-V)

| ID | Label |
|---|---|
| 10 | nOS-V task id of the RUNNING thread |
| 11 | nOS-V task type of the RUNNING thread *(default)* |
| 12 | nOS-V task body source |
| 13 | nOS-V subsystem |

## Project structure

```
prv-vstats/
├── prv_vstats/
│   ├── parser.py      — .prv / .pcf / .row readers
│   ├── stats.py       — interval reconstruction and statistics
│   └── llm_export.py  — LLM-friendly text export
├── prvvstats.py       — CLI entry point
└── requirements.txt
```

See `MANUAL.md` for the full reference manual.
