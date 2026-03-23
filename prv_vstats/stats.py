import pandas as pd


def compute_intervals(events, event_type_filter):
    """
    Reconstruct task execution intervals from raw events.

    Returns list of dicts: {row, value, start_ns, end_ns, duration_ns}
    """
    # Filter and sort by time
    filtered = [(row, time, etype, value)
                for (row, time, etype, value) in events
                if etype == event_type_filter]
    filtered.sort(key=lambda x: (x[1], x[0]))  # sort by time, then row

    active = {}  # row -> (value, start_time)
    intervals = []

    for row, time, etype, value in filtered:
        if value != 0:
            # Close any existing interval for this row
            if row in active:
                prev_value, prev_start = active[row]
                intervals.append({
                    "row": row,
                    "value": prev_value,
                    "start_ns": prev_start,
                    "end_ns": time,
                    "duration_ns": time - prev_start,
                })
            active[row] = (value, time)
        else:
            # Close interval
            if row in active:
                prev_value, prev_start = active[row]
                intervals.append({
                    "row": row,
                    "value": prev_value,
                    "start_ns": prev_start,
                    "end_ns": time,
                    "duration_ns": time - prev_start,
                })
                del active[row]

    return intervals


def compute_stats(intervals, duration_ns, nrows, row_names, pcf_values):
    """
    Compute global and per-thread statistics.

    Returns {"global": DataFrame, "per_thread": DataFrame}
    """
    if not intervals:
        empty = pd.DataFrame(columns=["task", "mean_ms", "median_ms",
                                       "p25_ms", "p75_ms", "count", "pct_timeline"])
        return {"global": empty, "per_thread": empty}

    df = pd.DataFrame(intervals)
    df["duration_ms"] = df["duration_ns"] / 1e6

    # Map value → task name
    df["task"] = df["value"].map(lambda v: pcf_values.get(v, str(v)))

    # Map row → row name
    def row_to_name(r):
        idx = r - 1
        if 0 <= idx < len(row_names):
            return row_names[idx]
        return f"Thread {r}"

    df["thread"] = df["row"].map(row_to_name)

    # Global stats: pool all threads, group by task
    def agg_stats(grp, total_ns):
        d = grp["duration_ns"]
        return pd.Series({
            "mean_ms": d.mean() / 1e6,
            "median_ms": d.median() / 1e6,
            "p25_ms": d.quantile(0.25) / 1e6,
            "p75_ms": d.quantile(0.75) / 1e6,
            "count": len(d),
            "pct_timeline": d.sum() / total_ns * 100,
        })

    global_stats = (
        df.groupby("task")
        .apply(agg_stats, total_ns=duration_ns * nrows, include_groups=False)
        .reset_index()
        .sort_values("pct_timeline", ascending=False)
    )

    # Per-thread stats: group by (thread, task)
    def agg_per_thread(grp):
        d = grp["duration_ns"]
        return pd.Series({
            "mean_ms": d.mean() / 1e6,
            "median_ms": d.median() / 1e6,
            "p25_ms": d.quantile(0.25) / 1e6,
            "p75_ms": d.quantile(0.75) / 1e6,
            "count": len(d),
            "pct_timeline": d.sum() / duration_ns * 100,
        })

    per_thread_stats = (
        df.groupby(["thread", "task"])
        .apply(agg_per_thread, include_groups=False)
        .reset_index()
        .sort_values(["thread", "pct_timeline"], ascending=[True, False])
    )

    return {"global": global_stats, "per_thread": per_thread_stats, "_df": df}
