import re


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


def parse_prv(prv_path, event_type_filter=None):
    """
    Returns (duration_ns: int, nrows: int, events: list[tuple])
    Each event tuple: (row: int, time: int, event_type: int, value: int)

    If event_type_filter is not None, only events with that event type are
    retained while parsing.
    """
    duration_ns = 0
    nrows = 0
    events = []

    with open(prv_path, encoding="latin-1") as f:
        for raw_line in f:
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

            # Format: 2:cpu:appl:task:thread:time:nfields:[type:value]+
            # Simpler: 2:0:1:1:row:time:type:value (may have multiple type:value pairs)
            try:
                row = int(parts[4])
                time = int(parts[5])
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
                    etype = int(tail[i])
                    evalue = int(tail[i + 1])
                    if event_type_filter is None or etype == event_type_filter:
                        events.append((row, time, etype, evalue))
            except (ValueError, IndexError):
                continue

    return duration_ns, nrows, events
