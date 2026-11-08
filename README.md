# P6-XER-to-Copilot

Turns a Primavera P6 schedule export into clean JSON that a Copilot agent can reason over, plus the agent prompt that tells it what to do with that JSON.

The idea is simple. Schedulers shouldn't have to open P6 to answer "what's on the critical path?" or "how much float is left on commissioning?". Export the schedule, run the parser, hand the JSON to the agent, ask questions in plain English.

## What's in the repo

```
parser/
  xer_to_json.py     reads a native .xer export and writes JSON
agent/
  instructions.md    system prompt for the "P6 Schedule Analyst" Copilot agent
tests/
  test_parser.py     unit tests
  fixtures/
    sample.xer       small made-up schedule used by the tests
```

## Running the parser

Python 3.9+ and the standard library, nothing to install.

```bash
python parser/xer_to_json.py schedule.xer                 # writes p6_analysis.json
python parser/xer_to_json.py schedule.xer -o hall2.json   # pick the output file
python parser/xer_to_json.py schedule.xer -o -            # JSON to stdout
```

Progress, warnings and errors go to stderr, so `-o -` gives you clean JSON you can pipe. It exits with 1 if the file is missing or isn't an XER, 0 otherwise. From Python, `parse_xer_file(path)` returns the same structure as a dict and raises `XerError` on bad input.

Export from P6 the normal way (File > Export > Primavera PM - (XER)). Windows-1252 and UTF-8 exports both work.

## How the XER is read

An XER is tab-delimited text with one table after another: `%T` gives the table name, `%F` the field names and `%R` one row. The parser uses five tables:

| Table | Used for |
|---|---|
| `PROJECT` | project short name, data date, planned and scheduled finish |
| `PROJWBS` | WBS names and the full WBS path for each activity. The project's display name also comes from here, from its root WBS node |
| `CALENDAR` | hours per day, used to turn hours into working days |
| `TASK` | the activities |
| `TASKPRED` | relationships |

P6 stores durations, float and lag in hours. Every one of them is converted to working days using the activity's own calendar, so 72 hours on a 24-hour commissioning calendar comes out as 3 days and on a standard 8-hour calendar it would be 9. Lag uses the successor's calendar, which is P6's default.

Activities are keyed on P6's internal `task_id` while parsing, but the JSON uses `task_code`, which is the Activity ID people actually see in P6. Relationships come out on both sides, so each activity has `predecessors` and `successors`. If a relationship points to an activity in a project that wasn't exported, it's kept as `external:<task_id>` and a warning is added.

## Output

Trimmed example from the sample file:

```json
{
  "projects": [
    {
      "proj_id": "101",
      "short_name": "LON-DC1",
      "name": "London DC1 - Hall 2 fit-out",
      "data_date": "2026-11-02T08:00",
      "planned_start": "2026-01-05T08:00",
      "must_finish_by": null,
      "scheduled_finish": "2026-12-18T17:00"
    }
  ],
  "activities": [
    {
      "id": "A1010",
      "name": "Energise HV switchgear",
      "project": "LON-DC1",
      "wbs_id": "202",
      "wbs_name": "HV switchgear",
      "wbs_path": "Electrical / HV switchgear",
      "type": "task_dependent",
      "status": "in_progress",
      "pct_complete": 40.0,
      "original_duration": 5.0,
      "remaining_duration": 3.0,
      "actual_start": "2026-10-28T08:00",
      "actual_finish": null,
      "early_start": "2026-11-02T08:00",
      "early_finish": "2026-11-04T17:00",
      "late_start": "2026-11-02T08:00",
      "late_finish": "2026-11-04T17:00",
      "planned_start": "2026-10-28T08:00",
      "planned_finish": "2026-11-03T17:00",
      "constraint": null,
      "constraint_date": null,
      "total_float": 0.0,
      "free_float": 0.0,
      "is_critical": true,
      "on_longest_path": true,
      "predecessors": [ { "id": "A1000", "type": "FS", "lag": 0.0 } ],
      "successors":   [ { "id": "A2000", "type": "SS", "lag": 2.0 } ]
    }
  ],
  "metadata": {
    "parsed_at": "2026-11-08T10:55:00",
    "source_file": "sample.xer",
    "p6_version": "19.12",
    "export_date": "2026-11-08",
    "activity_count": 4,
    "relationship_count": 4,
    "units": "durations, float and lag in working days",
    "warnings": ["1 relationship(s) point to activities not in this file"]
  }
}
```

A few fields need explaining:

- `status` is `not_started`, `in_progress` or `complete`. `type` is the P6 activity type in plain words (`task_dependent`, `finish_milestone`, `level_of_effort` and so on).
- `is_critical` follows P6's default rule: total float of zero or less on an activity that isn't complete. `on_longest_path` is P6's own longest-path flag, as it stood at the last schedule run.
- `planned_start` and `planned_finish` are P6's planned dates on the current project. They are not the baseline (see below).
- All dates are ISO 8601 to the minute. Anything blank in P6 comes out as `null`.

## Setting up the agent

Paste `agent/instructions.md` into the instructions field of a Copilot Studio agent (or whatever host you're using), then give it the JSON either as an uploaded file or through an action that runs the parser. The prompt describes the JSON and how to read it: units, what counts as critical, how to treat external links and which activity types to leave out of logic checks.

## Tests

```bash
python -m unittest discover -s tests -v
```

`tests/fixtures/sample.xer` is a hand-built four-activity schedule. It has two calendars, a nested WBS, a complete, an in-progress and a not-started activity, a finish milestone with a constraint, FS/SS/FF links with lag, negative float and one link to another project. It's saved as Windows-1252 with CRLF line endings, like a real export. Real `.xer` files are git-ignored everywhere except `tests/fixtures/`, so live project schedules don't end up in the repo by accident.

## Known gaps

- No baseline comparison yet. An XER only carries baseline dates if the baseline project is exported alongside the current one, and the parser doesn't link the two.
- P20/P50/P80 finish dates are gone from the output. They don't exist in an XER at all and would need importing from the risk tool (Primavera Risk Analysis, Safran Risk or similar) as a separate file.
- Resources, costs, activity codes, UDFs and steps (the `TASKRSRC`, `ACTVCODE`, `UDFVALUE` and related tables) are ignored for now.
- When a file holds several projects, all their activities go into one list with a `project` field on each. Nothing filters by project yet.
- Only tested against the hand-built sample so far. It should be run against a few real exports from different P6 versions before anyone relies on it.
- `agent/instructions.md` describes the data but still doesn't say what analysis to run (critical path summary, float erosion, logic checks such as open ends, and so on) or what the answers should look like.

## Licence

Private repo, no licence set.
