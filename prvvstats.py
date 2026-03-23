#!/usr/bin/env python3
"""prv-vstats: Paraver trace statistical analysis tool."""

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

from prv_vstats.parser import parse_pcf, parse_row, parse_prv
from prv_vstats.stats import compute_intervals, compute_stats
from prv_vstats.llm_export import format_llm


def build_color_palette(task_names):
    cmap = plt.get_cmap("tab20")
    return {name: cmap(i % 20) for i, name in enumerate(sorted(task_names))}


def plot_figure(stats_result, output_path):
    df = stats_result["_df"]
    global_df = stats_result["global"]
    per_thread_df = stats_result["per_thread"]

    task_names = sorted(df["task"].unique())
    palette = build_color_palette(task_names)

    threads = sorted(df["thread"].unique())

    fig, (ax_top, ax_bot) = plt.subplots(
        2, 1,
        figsize=(max(12, len(task_names) * 2), 10),
        gridspec_kw={"height_ratios": [2, 1.5]},
    )

    # --- Top panel: violin plot per task type ---
    positions = range(len(task_names))
    for i, task in enumerate(task_names):
        data = df[df["task"] == task]["duration_ms"].values
        if len(data) < 2:
            ax_top.scatter([i], data, color=palette[task], zorder=3)
            continue
        parts = ax_top.violinplot(data, positions=[i], showmeans=False,
                                   showmedians=False, showextrema=True)
        for pc in parts["bodies"]:
            pc.set_facecolor(palette[task])
            pc.set_alpha(0.7)
        for part_name in ("cbars", "cmins", "cmaxes"):
            if part_name in parts:
                parts[part_name].set_edgecolor(palette[task])
        # Mean dot
        ax_top.scatter([i], [data.mean()], color="white", edgecolors=palette[task],
                       zorder=3, s=40, linewidths=1.5, label="_nolegend_")

    ax_top.set_xticks(list(positions))
    ax_top.set_xticklabels(task_names, rotation=30, ha="right", fontsize=8)
    ax_top.set_ylabel("Duration (ms)")
    ax_top.set_title("Task duration distribution (violin, dot = mean)")
    ax_top.grid(axis="y", linestyle="--", alpha=0.4)

    # --- Bottom panel: stacked horizontal bar chart ---
    # For each thread, sum pct_timeline per task
    bar_data = {}
    for task in task_names:
        bar_data[task] = []
        for thread in threads:
            row = per_thread_df[(per_thread_df["thread"] == thread) &
                                (per_thread_df["task"] == task)]
            bar_data[task].append(row["pct_timeline"].values[0] if len(row) else 0.0)

    y_pos = np.arange(len(threads))
    lefts = np.zeros(len(threads))
    for task in task_names:
        vals = np.array(bar_data[task])
        ax_bot.barh(y_pos, vals, left=lefts, color=palette[task],
                    label=task, height=0.6)
        lefts += vals

    ax_bot.set_yticks(y_pos)
    ax_bot.set_yticklabels(threads, fontsize=7)
    ax_bot.set_xlabel("% of thread timeline")
    ax_bot.set_title("Per-thread task breakdown")
    ax_bot.set_xlim(0, max(100, lefts.max() * 1.05))
    ax_bot.grid(axis="x", linestyle="--", alpha=0.4)

    # Legend outside
    handles = [mpatches.Patch(color=palette[t], label=t) for t in task_names]
    ax_bot.legend(handles=handles, bbox_to_anchor=(1.01, 1), loc="upper left",
                  fontsize=7, frameon=True)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Figure saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Paraver trace statistical analysis tool"
    )
    parser.add_argument("prv", help="Path to .prv trace file")
    parser.add_argument("--event-type", type=int, default=11,
                        help="Event type ID to analyse (default: 11, nOS-V task type)")
    parser.add_argument("--output", default="stats.png",
                        help="Output figure path (default: stats.png)")
    parser.add_argument("--llm-output", metavar="FILE", default=None,
                        help="Write LLM-friendly text export to FILE (use '-' for stdout)")
    args = parser.parse_args()

    prv_path = Path(args.prv)
    if not prv_path.exists():
        print(f"Error: {prv_path} not found", file=sys.stderr)
        sys.exit(1)

    pcf_path = prv_path.with_suffix(".pcf")
    row_path = prv_path.with_suffix(".row")

    print(f"Parsing {prv_path} ...")
    duration_ns, nrows, events = parse_prv(prv_path)
    print(f"  Duration: {duration_ns / 1e9:.3f} s  |  Rows: {nrows}  |  Events: {len(events)}")

    pcf_data = {}
    row_names = []

    if pcf_path.exists():
        print(f"Parsing {pcf_path} ...")
        pcf_data = parse_pcf(pcf_path)
    else:
        print(f"Warning: {pcf_path} not found — value names will be numeric", file=sys.stderr)

    if row_path.exists():
        print(f"Parsing {row_path} ...")
        row_names = parse_row(row_path)
    else:
        print(f"Warning: {row_path} not found — thread names will be generic", file=sys.stderr)

    pcf_values = {}
    if args.event_type in pcf_data:
        pcf_values = pcf_data[args.event_type]["values"]
        label = pcf_data[args.event_type]["label"]
        print(f"Event type {args.event_type}: '{label}' ({len(pcf_values)} values)")
    else:
        print(f"Event type {args.event_type} not found in PCF — values shown as integers")

    print(f"Computing intervals for event type {args.event_type} ...")
    intervals = compute_intervals(events, args.event_type)
    print(f"  Found {len(intervals)} intervals")

    if not intervals:
        print("No intervals found. Check --event-type value.", file=sys.stderr)
        sys.exit(1)

    print("Computing statistics ...")
    result = compute_stats(intervals, duration_ns, nrows, row_names, pcf_values)

    print("\n" + "=" * 70)
    print("GLOBAL STATISTICS (all threads pooled)")
    print("=" * 70)
    print(result["global"].to_string(index=False, float_format="{:.4f}".format))

    print("\n" + "=" * 70)
    print("PER-THREAD STATISTICS")
    print("=" * 70)
    print(result["per_thread"].to_string(index=False, float_format="{:.4f}".format))

    print("\nGenerating figure ...")
    plot_figure(result, args.output)

    if args.llm_output is not None:
        event_label = pcf_data.get(args.event_type, {}).get("label", f"event type {args.event_type}")
        print("Generating LLM export ...")
        llm_text = format_llm(result, duration_ns, prv_path.name, event_label, args.event_type)
        if args.llm_output == "-":
            sys.stdout.write(llm_text)
        else:
            Path(args.llm_output).write_text(llm_text, encoding="utf-8")
            print(f"LLM export written to {args.llm_output}")


if __name__ == "__main__":
    main()
