"""
Trim a prosperity4bt .log toward official IMC *test-upload* size:
  1000 steps x 2 products -> ~2000 activity rows (typical on prosperity.equirag.com).

`prosperity4bt trader.py 0` uses full bundled data: 10_000 steps/day x 2 days.
That is not wrong — it is a longer run than the website's ~1000-step test.

Usage:
  python trim_log_for_visualizer.py INPUT.log OUTPUT.log
  python trim_log_for_visualizer.py INPUT.log OUTPUT.log --ticks 1000 --day -2
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def iter_json_objects(blob: str):
    i, n = 0, len(blob)
    while i < n:
        if blob[i] != "{":
            i += 1
            continue
        depth, j = 0, i
        while j < n:
            c = blob[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    yield blob[i : j + 1]
                    i = j + 1
                    break
            j += 1
        else:
            return


def trim_sandbox(sandbox_section: str, max_ts: int) -> str:
    if "Sandbox logs:" not in sandbox_section:
        return sandbox_section.rstrip() + "\n"
    _, _, rest = sandbox_section.partition("Sandbox logs:")
    rest = rest.lstrip()
    kept = []
    for obj in iter_json_objects(rest):
        m = re.search(r'"timestamp"\s*:\s*(\d+)', obj)
        if m and int(m.group(1)) <= max_ts:
            kept.append(obj)
    return "Sandbox logs:\n" + "\n".join(kept) + "\n"


def trim_activities_lines(lines: list[str], day: int, max_ticks: int) -> str:
    max_ts = (max_ticks - 1) * 100
    if not lines:
        return ""
    out = [lines[0]]
    for line in lines[1:]:
        p = line.split(";")
        if len(p) < 3:
            continue
        if int(p[0]) == day and int(p[1]) <= max_ts:
            out.append(line)
    return "\n".join(out) + "\n"


def trim_trades_json(text: str, max_ts: int) -> str:
    text = text.strip()
    text = re.sub(r",\s*}", "}", text)
    text = re.sub(r",\s*]", "]", text)
    trades = json.loads(text)
    kept = [t for t in trades if int(t.get("timestamp", 0)) <= max_ts]
    return json.dumps(kept, indent=2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--ticks", type=int, default=1000)
    ap.add_argument("--day", type=int, default=-2)
    args = ap.parse_args()

    raw = args.input.read_text(encoding="utf-8", errors="replace")
    idx_act = raw.find("Activities log:\n")
    idx_trade = raw.find("Trade History:\n")
    if idx_act == -1 or idx_trade == -1:
        print("Missing Activities log or Trade History section.", file=sys.stderr)
        sys.exit(1)

    max_ts = (args.ticks - 1) * 100

    sandbox_part = raw[:idx_act].rstrip() + "\n"
    act_start = idx_act + len("Activities log:\n")
    activities_csv = raw[act_start:idx_trade].strip()
    act_lines = activities_csv.splitlines()
    if not act_lines or not act_lines[0].startswith("day;"):
        print("Unexpected Activities CSV (missing day; header).", file=sys.stderr)
        sys.exit(1)
    act_body_lines = act_lines[1:]

    trades_blob = raw[idx_trade:].strip()
    if not trades_blob.startswith("Trade History:"):
        print("Unexpected Trade History format.", file=sys.stderr)
        sys.exit(1)
    trades_json = trades_blob.split("\n", 1)[1].strip()

    out = (
        trim_sandbox(sandbox_part, max_ts).rstrip()
        + "\n\n"
        + "Activities log:\n"
        + trim_activities_lines(act_lines, args.day, args.ticks).rstrip()
        + "\n\n"
        + "Trade History:\n"
        + trim_trades_json(trades_json, max_ts)
        + "\n"
    )

    args.output.write_text(out, encoding="utf-8")

    kept = sum(
        1
        for line in act_body_lines
        if len(line.split(";")) >= 3 and int(line.split(";")[0]) == args.day and int(line.split(";")[1]) <= max_ts
    )
    print(f"Wrote {args.output}")
    print(f"  Activity data rows: {kept} (~{2 * args.ticks} when 2 products each step)")
    print(f"  day={args.day}, ticks={args.ticks}, max_timestamp={max_ts}")


if __name__ == "__main__":
    main()
