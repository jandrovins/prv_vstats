"""LLM-friendly text export for prv-vstats trace analysis results."""

import sys

# Abbreviation pools — chosen for visual distinctiveness
_UPPER_POOL = "MSDWABCEFGHIJKLNOPQRTUVXYZ"
_LOWER_POOL = "abcdefghijklmnopqrstuvwxyz"


def _build_abbrev_map(global_df):
    """Map task names to single-char abbreviations (or None for bracket form)."""
    tasks = global_df["task"].tolist()  # already sorted desc by pct_timeline
    abbrev_map = {}
    for rank, task in enumerate(tasks):
        if rank < 5:
            abbrev_map[task] = _UPPER_POOL[rank]
        elif rank < 10:
            abbrev_map[task] = _LOWER_POOL[rank - 5]
        else:
            abbrev_map[task] = None
    return abbrev_map


def _task_token(task, abbrev_map):
    abbrev = abbrev_map.get(task)
    if abbrev is not None:
        return abbrev
    name = task[:30] + ("…" if len(task) > 30 else "")
    return f"[{name}]"


def _build_legend_section(global_df, abbrev_map):
    lines = ["=== TASK LEGEND ==="]
    n_bracket = 0
    for _, row in global_df.iterrows():
        task = row["task"]
        abbrev = abbrev_map.get(task)
        if abbrev is not None:
            lines.append(
                f"  {abbrev} = {task:<44} mean={row['mean_ms']:.1f}ms  pct={row['pct_timeline']:.1f}%"
            )
        else:
            n_bracket += 1
    if n_bracket:
        lines.append(f"  (remaining {n_bracket} task(s) shown by full name in [brackets])")
    return "\n".join(lines)


def _build_global_stats_section(global_df):
    table = global_df.to_string(index=False, float_format="{:.2f}".format)
    return "=== GLOBAL STATS (all threads pooled) ===\n" + table


def _build_per_thread_stats_section(per_thread_df):
    table = per_thread_df.to_string(index=False, float_format="{:.2f}".format)
    return (
        "=== PER-THREAD STATS (violin plot data) ===\n"
        "Columns: thread | task | mean_ms | median_ms | p25_ms | p75_ms | count | pct_timeline\n"
        + table
    )


def _build_thread_sequences_section(df, duration_ns, abbrev_map, idle_threshold_ms):
    t0_ns = int(df["start_ns"].min())
    threads_sorted = sorted(df["thread"].unique())
    max_name_len = max(len(t) for t in threads_sorted)

    lines = [
        "=== THREAD SEQUENCES (format: ABBREV@start_ms(duration_ms)) ===",
        f"  t=0 corresponds to first event at absolute time {t0_ns} ns",
        f"  Idle gaps > {idle_threshold_ms} ms shown as .@start(duration)",
    ]

    idle_ns = idle_threshold_ms * 1e6

    for thread in threads_sorted:
        tdf = df[df["thread"] == thread].sort_values("start_ns")
        busy_pct = tdf["duration_ns"].sum() / duration_ns * 100

        tokens = []
        prev_end_ns = t0_ns

        for _, interval in tdf.iterrows():
            start_ns = int(interval["start_ns"])
            end_ns = int(interval["end_ns"])
            dur_ms = interval["duration_ns"] / 1e6

            gap_ns = start_ns - prev_end_ns
            if gap_ns > idle_ns:
                gap_start_ms = (prev_end_ns - t0_ns) / 1e6
                tokens.append(f".@{gap_start_ms:.3f}({gap_ns / 1e6:.2f})")

            t_start_ms = (start_ns - t0_ns) / 1e6
            tokens.append(f"{_task_token(interval['task'], abbrev_map)}@{t_start_ms:.3f}({dur_ms:.2f})")
            prev_end_ns = end_ns

        seq = " ".join(tokens)
        lines.append(f"{thread:<{max_name_len}} [busy={busy_pct:.1f}%]: {seq}")

    return "\n".join(lines)


def format_llm(
    result,
    duration_ns,
    trace_name,
    event_label,
    event_type,
    idle_threshold_ms=0.1,
    size_warn_bytes=600_000,
):
    """
    Render a complete LLM-friendly text export of a trace analysis result.

    Parameters
    ----------
    result : dict
        Return value of compute_stats(). Must contain "global", "per_thread", "_df".
    duration_ns : int
        Trace duration in nanoseconds.
    trace_name : str
        Display name for the trace (typically the .prv filename).
    event_label : str
        Human-readable label for the event type (from PCF).
    event_type : int
        Numeric event type ID.
    idle_threshold_ms : float
        Minimum idle gap (ms) to emit an idle token. Default 0.1 ms.
    size_warn_bytes : int
        Warn if estimated output size exceeds this. Default 600 KB.

    Returns
    -------
    str
        Complete formatted text.
    """
    assert "_df" in result, "format_llm requires compute_stats() result with '_df' key"

    df = result["_df"]
    global_df = result["global"]
    per_thread_df = result["per_thread"]

    n_intervals = len(df)
    n_threads = df["thread"].nunique()
    duration_s = duration_ns / 1e9

    # Size estimate and warning
    estimated_bytes = n_intervals * 15 + 4096
    warning_line = ""
    if estimated_bytes > size_warn_bytes:
        msg = (
            f"WARNING: estimated output ~{estimated_bytes // 1024} KB "
            f"({n_intervals:,} intervals). Consider shortening the trace further."
        )
        print(msg, file=sys.stderr)
        warning_line = f"!! {msg}\n"

    abbrev_map = _build_abbrev_map(global_df)

    header = (
        f"=== TRACE: {trace_name} ===\n"
        f"Duration: {duration_s:.3f}s | Threads: {n_threads} | Intervals: {n_intervals:,}\n"
        f"Event type {event_type}: {event_label}\n"
        f"{warning_line}"
    ).rstrip("\n")

    sections = [
        header,
        _build_legend_section(global_df, abbrev_map),
        _build_global_stats_section(global_df),
        _build_per_thread_stats_section(per_thread_df),
        _build_thread_sequences_section(df, duration_ns, abbrev_map, idle_threshold_ms),
    ]

    return "\n\n".join(sections) + "\n"
