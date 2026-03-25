import os
import re
import sys
import time


def _format_bytes(nbytes):
    if nbytes is None:
        return "?"
    value = float(nbytes)
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)}{unit}"
            return f"{value:.1f}{unit}"
        value /= 1024.0
    return f"{int(nbytes)}B"


def _format_eta(seconds):
    if seconds is None:
        return "--:--"
    seconds = max(0, int(seconds))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _read_mem_total_bytes():
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    return int(parts[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _read_rss_bytes():
    try:
        with open("/proc/self/status", encoding="ascii") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    return int(parts[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _print_parse_progress(
    *,
    bytes_read,
    total_bytes,
    elapsed_s,
    lines_read,
    type2_records,
    event_pairs_seen,
    events_kept,
    mem_total_bytes,
    done=False,
):
    pct = (bytes_read / total_bytes * 100.0) if total_bytes > 0 else 0.0
    speed = bytes_read / elapsed_s if elapsed_s > 0 else 0.0
    eta = (total_bytes - bytes_read) / speed if speed > 0 and total_bytes > 0 else None

    rss = _read_rss_bytes()
    if rss is not None and mem_total_bytes:
        mem_pct = rss / mem_total_bytes * 100.0
        mem_part = f"RSS {_format_bytes(rss)}/{_format_bytes(mem_total_bytes)} ({mem_pct:.1f}%)"
    elif rss is not None:
        mem_part = f"RSS {_format_bytes(rss)}"
    else:
        mem_part = "RSS ?"

    msg = (
        f"  [PRV] {pct:6.2f}% {_format_bytes(bytes_read)}/{_format_bytes(total_bytes)}"
        f" | ETA {_format_eta(eta)}"
        f" | {speed / (1024 * 1024):6.1f} MB/s"
        f" | lines {lines_read:,}"
        f" | rec2 {type2_records:,}"
        f" | pairs {event_pairs_seen:,}"
        f" | kept {events_kept:,}"
        f" | {mem_part}"
    )
    end = "\n" if done else ""
    print(f"\r{msg}", end=end, file=sys.stderr, flush=True)


def parse_pcf(pcf_path):
    """
    Returns {event_type_id: {"label": str, "values": {value_id: name}}}
    """
    result = {}
    current_type_id = None
    current_label = None
    in_values = False

    with open(pcf_path, encoding="latin-1") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")
            stripped = line.strip()

            # Blank line resets state
            if stripped == "":
                in_values = False
                current_type_id = None
                current_label = None
                continue

            if stripped.startswith("EVENT_TYPE"):
                in_values = False
                current_type_id = None
                current_label = None
                continue

            if stripped.startswith("VALUES"):
                in_values = True
                continue

            if in_values and current_type_id is not None:
                # value lines: "value_id  name"
                parts = stripped.split(None, 1)
                if len(parts) == 2:
                    try:
                        vid = int(parts[0])
                        result[current_type_id]["values"][vid] = parts[1].strip()
                    except ValueError:
                        pass
                continue

            if not in_values and current_type_id is None:
                # Could be an event type definition line: "color type_id label"
                parts = stripped.split(None, 2)
                if len(parts) >= 2:
                    try:
                        type_id = int(parts[1])
                        label = parts[2].strip() if len(parts) == 3 else ""
                        current_type_id = type_id
                        current_label = label
                        result[type_id] = {"label": label, "values": {}}
                    except (ValueError, IndexError):
                        pass

    return result


def parse_row(row_path):
    """
    Returns list of row name strings (index 0 = row 1).
    """
    names = []
    found = False
    remaining = 0

    with open(row_path, encoding="latin-1") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not found:
                # Look for: LEVEL THREAD SIZE N
                m = re.match(r"LEVEL\s+THREAD\s+SIZE\s+(\d+)", line, re.IGNORECASE)
                if m:
                    remaining = int(m.group(1))
                    found = True
            else:
                if remaining > 0 and line:
                    names.append(line)
                    remaining -= 1
                if remaining == 0:
                    break

    return names


def parse_prv(prv_path, event_type_filter=None, show_progress=False, progress_interval_s=0.5):
    """
    Returns (duration_ns: int, nrows: int, events: list[tuple])
    Each event tuple: (row: int, time: int, event_type: int, value: int)

    If event_type_filter is not None, only events with that event type are
    retained while parsing.

    If show_progress is True, emits periodic progress updates to stderr while
    reading the .prv file.
    """
    duration_ns = 0
    nrows = 0
    events = []

    total_bytes = os.path.getsize(prv_path) if show_progress else 0
    mem_total_bytes = _read_mem_total_bytes() if show_progress else None
    start_t = time.monotonic()
    last_update_t = start_t
    bytes_read = 0
    lines_read = 0
    type2_records = 0
    event_pairs_seen = 0
    events_kept = 0

    with open(prv_path, "rb") as f:
        for raw_line_bytes in f:
            bytes_read += len(raw_line_bytes)
            lines_read += 1
            raw_line = raw_line_bytes.decode("latin-1", errors="replace")
            line = raw_line.strip()

            if line.startswith("#Paraver"):
                # Header: #Paraver (date):DURATION_ns:0:1:1(NROWS:0)
                # Duration may have _ns suffix: e.g. 48412874433_ns
                m = re.search(r"\):(\d+)(?:_ns)?:", line)
                if m:
                    duration_ns = int(m.group(1))
                # nrows: last occurrence of (N: pattern before end
                m2 = re.search(r"\((\d+):\d+\)\s*$", line)
                if m2:
                    nrows = int(m2.group(1))
                continue

            if line.startswith("#"):
                continue

            if not line:
                continue

            # Event line: record_type:...
            parts = line.split(":")
            if len(parts) < 8:
                continue
            try:
                record_type = int(parts[0])
            except ValueError:
                continue

            if record_type != 2:
                continue

            type2_records += 1

            # Format: 2:cpu:appl:task:thread:time:nfields:[type:value]+
            # Simpler: 2:0:1:1:row:time:type:value (may have multiple type:value pairs)
            try:
                row = int(parts[4])
                event_time = int(parts[5])
                # Remaining fields are type:value pairs
                tail = parts[6:]
                # tail[0] might be nfields or first type — detect by checking if it's
                # followed by pairs
                # The format after time is: [type:value]+ with no nfields in ovni traces
                # But some traces have nfields. We try: if len(tail) is odd → no nfields;
                # if even → first element might be nfields. Just collect all pairs.
                if len(tail) % 2 == 1:
                    # First element could be nfields — skip it
                    tail = tail[1:]
                for i in range(0, len(tail) - 1, 2):
                    event_pairs_seen += 1
                    etype = int(tail[i])
                    evalue = int(tail[i + 1])
                    if event_type_filter is None or etype == event_type_filter:
                        events.append((row, event_time, etype, evalue))
                        events_kept += 1
            except (ValueError, IndexError):
                continue

            if show_progress:
                now = time.monotonic()
                if now - last_update_t >= progress_interval_s:
                    _print_parse_progress(
                        bytes_read=bytes_read,
                        total_bytes=total_bytes,
                        elapsed_s=now - start_t,
                        lines_read=lines_read,
                        type2_records=type2_records,
                        event_pairs_seen=event_pairs_seen,
                        events_kept=events_kept,
                        mem_total_bytes=mem_total_bytes,
                        done=False,
                    )
                    last_update_t = now

    if show_progress:
        _print_parse_progress(
            bytes_read=bytes_read,
            total_bytes=total_bytes,
            elapsed_s=max(time.monotonic() - start_t, 1e-9),
            lines_read=lines_read,
            type2_records=type2_records,
            event_pairs_seen=event_pairs_seen,
            events_kept=events_kept,
            mem_total_bytes=mem_total_bytes,
            done=True,
        )

    return duration_ns, nrows, events
