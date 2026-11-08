# P6-XER-to-Copilot

Turns a Primavera P6 schedule export into clean JSON that a Copilot agent can reason over, plus the agent prompt that tells it what to do with that JSON.

The idea is simple. Schedulers shouldn't have to open P6 to answer "what's on the critical path?" or "how much float is left on commissioning?". Export the schedule, run the parser, hand the JSON to the agent, ask questions in plain English.

## What's in the repo

```
parser/
  xer_to_json.py     reads a P6 export and writes structured JSON to stdout
agent/
  instructions.md    system prompt for the "P6 Schedule Analyst" Copilot agent
```

## Running the parser

Needs Python 3.9+ and nothing outside the standard library.

```bash
python parser/xer_to_json.py path/to/schedule.xer > schedule.json
```

Output looks like this (trimmed):

```json
{
  "project": { "...": "project-level fields from the export" },
  "activities": [
    {
      "ID": "A1000",
      "Name": "Energise HV switchgear",
      "Status": "NOT_STARTED",
      "PctComplete": 0.0,
      "Duration": 10.0,
      "EarlyStart": "2024-01-01",
      "EarlyFinish": "2024-01-11",
      "TotalFloat": 0.0,
      "IsCritical": true,
      "BaselineFinish": "...",
      "P20Finish": "...",
      "P50Finish": "...",
      "P80Finish": "...",
      "Predecessors": [ { "ID": "A0990", "Type": "FS", "Lag": 0.0 } ]
    }
  ],
  "metadata": { "parsed_at": "2026-11-08T10:00:00", "activity_count": 1 }
}
```

If anything goes wrong the script prints `{"error": "..."}` and exits normally, so check for that key before passing the output on.

## Setting up the agent

Paste the contents of `agent/instructions.md` into the instructions field of a Copilot Studio agent (or whatever host you're using), then give it the JSON either as an uploaded file or via an action that calls the parser. The prompt sets the agent up as a P6 scheduler and risk analyst and describes the JSON shape it should expect.

The P20/P50/P80 fields are there for risk-adjusted finish dates from a Monte Carlo run (Primavera Risk Analysis, Safran Risk or similar). If your export doesn't carry them they come through as `null` and the agent should just ignore them.

## Known gaps

Worth reading before relying on any of this.

- **It doesn't read native .xer files yet.** Despite the name, `xer_to_json.py` parses XML. A real XER file is tab-delimited text (`%T` table, `%F` fields, `%R` rows), so feeding one in will return a parse error. It also isn't quite P6's PMXML format, which uses tags like `Activity`, `Id` and `Name` rather than `ACTIVITY`, `ACTIVITY_ID` and `ACTIVITY_NAME`. Right now it only works on XML matching its own tag names. A proper XER reader would pull from the `PROJECT`, `TASK`, `TASKPRED` and `CALENDAR` tables.
- Durations and float are passed through as-is. XER stores these in hours, so they'll need converting to days against the activity calendar.
- `agent/instructions.md` stops partway through the input schema. It still needs the actual analysis tasks (critical path summary, float erosion, baseline slippage, logic checks such as open ends and negative lag) and some guidance on output format.
- No tests or sample data yet. Sample XER files are git-ignored on purpose so live project schedules don't end up in the repo; anonymised fixtures can go under `tests/fixtures/`.

## Licence

Private repo, no licence set.
