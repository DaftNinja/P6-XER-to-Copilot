"""
Convert an Oracle Primavera P6 .xer export into JSON for the Copilot agent.

XER format, briefly
-------------------
An XER file is tab-delimited text. Each line starts with a marker:

    ERMHDR  header line (P6 version, export date, user, currency ...)
    %T      start of a table, e.g. "%T<tab>TASK"
    %F      field names for that table
    %R      one data row
    %E      end of file

The tables this script uses:

    PROJECT   proj_id, proj_short_name, last_recalc_date (data date) ...
    CALENDAR  clndr_id, clndr_name, day_hr_cnt (hours per working day)
    PROJWBS   wbs_id, parent_wbs_id, wbs_short_name, wbs_name, proj_node_flag
    TASK      activities. task_id is P6's internal key; task_code is the
              Activity ID users see in P6.
    TASKPRED  relationships. task_id is the successor, pred_task_id the
              predecessor, both internal keys. pred_type is PR_FS/SS/FF/SF.

Durations, float and lag are stored in hours. They are converted to working
days using the activity's calendar (falling back to 8 hours/day).

Usage
-----
    python xer_to_json.py schedule.xer               # writes p6_analysis.json
    python xer_to_json.py schedule.xer -o out.json
    python xer_to_json.py schedule.xer -o -          # JSON to stdout
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime

DEFAULT_HOURS_PER_DAY = 8.0

STATUS_MAP = {
    "TK_NotStart": "not_started",
    "TK_Active": "in_progress",
    "TK_Complete": "complete",
}

TASK_TYPE_MAP = {
    "TT_Task": "task_dependent",
    "TT_Rsrc": "resource_dependent",
    "TT_Mile": "start_milestone",
    "TT_FinMile": "finish_milestone",
    "TT_LOE": "level_of_effort",
    "TT_WBS": "wbs_summary",
}

RELATION_MAP = {"PR_FS": "FS", "PR_SS": "SS", "PR_FF": "FF", "PR_SF": "SF"}


class XerError(Exception):
    pass


# --------------------------------------------------------------------------
# Low-level reading
# --------------------------------------------------------------------------

def read_xer_text(file_path):
    """XER exports are usually Windows-1252, sometimes UTF-8. Try UTF-8 first."""
    with open(file_path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")  # never fails


def read_tables(text):
    """Return {table_name: [row_dict, ...]} and the ERMHDR fields."""
    tables = defaultdict(list)
    header = []
    current = None
    fields = []

    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        # Don't strip the whole line: trailing tabs are empty fields.
        parts = line.rstrip("\r\n").split("\t")
        marker = parts[0]

        if marker == "ERMHDR":
            header = parts[1:]
        elif marker == "%T":
            current = parts[1].strip() if len(parts) > 1 else None
            fields = []
            if current:
                tables.setdefault(current, [])
        elif marker == "%F":
            fields = [p.strip() for p in parts[1:]]
        elif marker == "%R":
            if not current or not fields:
                raise XerError(f"Line {lineno}: data row before table/field definition")
            values = parts[1:]
            row = {}
            for i, name in enumerate(fields):
                val = values[i] if i < len(values) else ""
                row[name] = val if val != "" else None
            tables[current].append(row)
        elif marker == "%E":
            break
        # anything else is ignored

    if not header and not tables:
        raise XerError("No ERMHDR line or %T tables found - this doesn't look like an XER file")
    return dict(tables), header


# --------------------------------------------------------------------------
# Value helpers
# --------------------------------------------------------------------------

def to_float(val):
    if val is None:
        return None
    try:
        return float(val)
    except ValueError:
        return None


def to_iso(val):
    """P6 writes dates as 'YYYY-MM-DD HH:MM'. Return ISO 8601, or None."""
    if not val:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(val, fmt).isoformat(timespec="minutes")
        except ValueError:
            continue
    return val  # leave unrecognised formats as they are


def hours_to_days(hours, hours_per_day):
    if hours is None:
        return None
    return round(hours / hours_per_day, 2)


# --------------------------------------------------------------------------
# Main conversion
# --------------------------------------------------------------------------

def parse_xer_file(file_path):
    """Parse an XER file. Returns a dict; raises XerError or OSError on failure."""
    if not os.path.exists(file_path):
        raise XerError(f"File not found: {file_path}")

    tables, header = read_tables(read_xer_text(file_path))
    warnings = []

    for required in ("PROJECT", "TASK"):
        if required not in tables:
            raise XerError(f"No {required} table in file")
    for optional in ("PROJWBS", "TASKPRED", "CALENDAR"):
        if optional not in tables:
            warnings.append(f"No {optional} table in file")

    # Calendars: hours per working day
    cal_hours = {}
    for c in tables.get("CALENDAR", []):
        hpd = to_float(c.get("day_hr_cnt"))
        cal_hours[c.get("clndr_id")] = hpd if hpd and hpd > 0 else DEFAULT_HOURS_PER_DAY

    # WBS: names and full path (excluding the project node itself)
    wbs = {w["wbs_id"]: w for w in tables.get("PROJWBS", []) if w.get("wbs_id")}

    def wbs_path(wbs_id):
        names, seen = [], set()
        while wbs_id in wbs and wbs_id not in seen:
            seen.add(wbs_id)
            node = wbs[wbs_id]
            if node.get("proj_node_flag") == "Y":
                break
            names.append(node.get("wbs_name") or node.get("wbs_short_name") or "")
            wbs_id = node.get("parent_wbs_id")
        return " / ".join(reversed(names)) or None

    # Project name lives on the project's root WBS node, not in PROJECT
    project_names = {
        w.get("proj_id"): w.get("wbs_name")
        for w in wbs.values() if w.get("proj_node_flag") == "Y"
    }

    projects = []
    proj_short = {}
    for p in tables["PROJECT"]:
        pid = p.get("proj_id")
        proj_short[pid] = p.get("proj_short_name")
        projects.append({
            "proj_id": pid,
            "short_name": p.get("proj_short_name"),
            "name": project_names.get(pid),
            "data_date": to_iso(p.get("last_recalc_date")),
            "planned_start": to_iso(p.get("plan_start_date")),
            "must_finish_by": to_iso(p.get("plan_end_date")),
            "scheduled_finish": to_iso(p.get("scd_end_date")),
        })

    # Activities
    activities = {}
    for t in tables["TASK"]:
        tid = t.get("task_id")
        if not tid:
            continue
        hpd = cal_hours.get(t.get("clndr_id"), DEFAULT_HOURS_PER_DAY)
        total_float = hours_to_days(to_float(t.get("total_float_hr_cnt")), hpd)
        status = STATUS_MAP.get(t.get("status_code"), t.get("status_code"))
        activities[tid] = {
            "id": t.get("task_code"),
            "name": t.get("task_name"),
            "project": proj_short.get(t.get("proj_id")),
            "wbs_id": t.get("wbs_id"),
            "wbs_name": wbs.get(t.get("wbs_id"), {}).get("wbs_name"),
            "wbs_path": wbs_path(t.get("wbs_id")),
            "type": TASK_TYPE_MAP.get(t.get("task_type"), t.get("task_type")),
            "status": status,
            "pct_complete": to_float(t.get("phys_complete_pct")) or 0.0,
            "calendar": t.get("clndr_id"),
            "original_duration": hours_to_days(to_float(t.get("target_drtn_hr_cnt")), hpd),
            "remaining_duration": hours_to_days(to_float(t.get("remain_drtn_hr_cnt")), hpd),
            "actual_start": to_iso(t.get("act_start_date")),
            "actual_finish": to_iso(t.get("act_end_date")),
            "early_start": to_iso(t.get("early_start_date")),
            "early_finish": to_iso(t.get("early_end_date")),
            "late_start": to_iso(t.get("late_start_date")),
            "late_finish": to_iso(t.get("late_end_date")),
            "planned_start": to_iso(t.get("target_start_date")),
            "planned_finish": to_iso(t.get("target_end_date")),
            "constraint": t.get("cstr_type"),
            "constraint_date": to_iso(t.get("cstr_date")),
            "total_float": total_float,
            "free_float": hours_to_days(to_float(t.get("free_float_hr_cnt")), hpd),
            # P6's default definition: total float <= 0 on an unfinished activity
            "is_critical": status != "complete" and total_float is not None and total_float <= 0,
            "on_longest_path": t.get("driving_path_flag") == "Y",
            "predecessors": [],
            "successors": [],
        }

    # Relationships
    unresolved = 0
    for r in tables.get("TASKPRED", []):
        succ, pred = activities.get(r.get("task_id")), activities.get(r.get("pred_task_id"))
        if succ is None and pred is None:
            unresolved += 1
            continue
        # P6 measures lag on the successor's calendar by default
        hpd = cal_hours.get((succ or pred)["calendar"], DEFAULT_HOURS_PER_DAY)
        rel = RELATION_MAP.get(r.get("pred_type"), r.get("pred_type"))
        lag = hours_to_days(to_float(r.get("lag_hr_cnt")), hpd) or 0.0
        pred_code = pred["id"] if pred else f"external:{r.get('pred_task_id')}"
        succ_code = succ["id"] if succ else f"external:{r.get('task_id')}"
        if pred is None or succ is None:
            unresolved += 1
        if succ is not None:
            succ["predecessors"].append({"id": pred_code, "type": rel, "lag": lag})
        if pred is not None:
            pred["successors"].append({"id": succ_code, "type": rel, "lag": lag})
    if unresolved:
        warnings.append(f"{unresolved} relationship(s) point to activities not in this file")

    activity_list = list(activities.values())
    for a in activity_list:
        a.pop("calendar")

    return {
        "projects": projects,
        "activities": activity_list,
        "metadata": {
            "parsed_at": datetime.now().isoformat(timespec="seconds"),
            "source_file": os.path.basename(file_path),
            "p6_version": header[0] if header else None,
            "export_date": header[1] if len(header) > 1 else None,
            "activity_count": len(activity_list),
            "relationship_count": len(tables.get("TASKPRED", [])),
            "units": "durations, float and lag in working days",
            "warnings": warnings,
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Convert a Primavera P6 .xer file to JSON.")
    ap.add_argument("xer_file")
    ap.add_argument("-o", "--output", default="p6_analysis.json",
                    help="output path, or - for stdout (default: p6_analysis.json)")
    args = ap.parse_args(argv)

    try:
        result = parse_xer_file(args.xer_file)
    except (XerError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output == "-":
        print(text)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        meta = result["metadata"]
        names = ", ".join(p["name"] or p["short_name"] or "?" for p in result["projects"])
        print(f"Parsed {meta['activity_count']} activities and "
              f"{meta['relationship_count']} relationships from {names}", file=sys.stderr)
        for w in meta["warnings"]:
            print(f"Warning: {w}", file=sys.stderr)
        print(f"JSON saved to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
