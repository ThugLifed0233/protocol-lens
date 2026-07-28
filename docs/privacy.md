# Personal data model

Apple Health exports can contain highly personal information. Protocol Lens keeps the working
dataset on the user’s Mac and separates it from files intended for GitHub.

## Local by default

Protocol Lens:

- reads files on the user’s machine;
- writes to a local DuckDB file;
- generates local reports;
- does not contain telemetry;
- does not require an account;
- does not upload Apple Health data.

The optional Google Sheets connector downloads a viewable sheet only when the user supplies its
link. It does not write back to the sheet.

## Repository boundary

The repository ignores:

```text
data/raw/*
data/processed/*
data/local/*
reports/*
```

Placeholder `.gitkeep` files are the only tracked contents of those folders.

Before every public contribution, run:

```bash
git status --short
```

Keep Apple exports, databases, reports, screenshots of personal metrics, logs, and temporary
extractions on the local Mac.

## Synthetic preview

The sample generator uses deterministic synthetic values. It contains no exported Apple records
and must not be presented as observed personal history.

## Supplement Lens and Personal Lab

The public research catalog contains evidence context, expected roles, metric-fit guidance, and
source links. It contains no personal usage dates or Apple measurements.

Personal Lab entries remain local unless all publication checks pass. A shareable snapshot
requires:

- a publishable profile;
- a confirmed, publishable usage period;
- an explicit experiment review.

The resulting snapshot contains:

- a reviewed intervention label;
- relative change and direction;
- observation counts and coverage;
- descriptive confidence and limitations.

It contains no exact dates, doses, notes, raw before/during/after values, or local identifiers.
Every snapshot requires review before it is added to GitHub.

## Workout aggregates

The public workout artifact contains only calendar aggregates. It excludes exact workout
timestamps, record identifiers, devices, source applications, and session rows. The local app can
still show individual sessions on the Mac.

## Reports

The report loads Plotly JavaScript from a public CDN when opened. Health values are embedded in
the local HTML and are not deliberately transmitted to that CDN. A future offline mode will bundle
the library.

## Removal

To remove locally processed data, delete only the intended database or report inside:

```text
data/processed/
data/local/
reports/
```

The original Apple export remains wherever the user saved it.
