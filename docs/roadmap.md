# Roadmap

## Now: Apple baseline

- [x] Stream Apple Health ZIP or XML.
- [x] Normalize selected signals, sleep, and workouts.
- [x] Store locally in DuckDB.
- [x] Make repeated full exports idempotent.
- [x] Generate trend and correlation views.
- [x] Compare workout and non-workout days.
- [x] Keep missing data visible.
- [x] Add a local web app that asks for data on first run.
- [x] Accept Excel, CSV, and viewable Google Sheets links.
- [ ] Validate against the first real Apple export.
- [ ] Add import diagnostics for unknown and malformed records.

## Next: better Apple exploration

- [ ] Workout detail with heart-rate samples inside each session.
- [ ] Select any two supported Apple metrics.
- [ ] Same month across years.
- [ ] Rolling 7-, 28-, and 90-day baselines.
- [ ] Heart-rate recovery and pace-efficiency views.
- [ ] Lagged correlations.
- [ ] Local offline Plotly bundle.
- [ ] Export a selected chart as PNG.

## Then: compound periods

- [x] Quick-add a supplement or nootropic interval.
- [x] Support broken usage periods.
- [ ] Dose events and product details.
- [x] Before / during / after windows.
- [ ] Compare repeated periods of the same compound.
- [x] Keep personal journal entries local by default.
- [x] Export reviewed summary JSON and CSV snapshots.

## Later: verified training history

- [ ] Powerlifting blocks as timeline intervals.
- [ ] RPE, volume, top-set, and back-off calculations.
- [ ] Strength trends from verified results.
- [ ] Apple workout overlay against lifting blocks.
- [ ] Recovery and training-load relationships.

## Explicitly not now

- cloud accounts;
- medical diagnosis;
- automatic medication recommendations;
- social features;
- a supplement marketplace;
- a single opaque health score;
- fabricated values for missing periods.
