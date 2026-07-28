# Personal Lab

Personal Lab connects a described intervention with one or more usage periods and Apple Health
signals. Profiles and periods are separate so uncertain historical dates do not weaken the
descriptive catalog.

## Profile

One profile answers:

- What is it?
- What was expected?
- Why was it tracked?
- Which color identifies it on the timeline?
- How confident are we in the reconstructed description?

Profiles do not claim that an expected outcome occurred.

## Usage period

An intervention can have any number of disconnected periods. Each period records:

- start and optional end date;
- optional dose and purpose notes;
- date confidence;
- personal-only or publishable-summary visibility.

Approximate and unverified periods remain visibly labelled. Missing dates are not invented.

## Apple outcome view

For a chosen intervention and Apple metric, the page shows:

1. the Apple metric across time;
2. shaded intervention periods;
3. a chosen usage period or all recorded periods;
4. period-focused, 30-day, 90-day, six-month, one-year, all-data, and custom windows;
5. equal before, during, and after comparisons;
6. relative change and observation counts;
7. data coverage and descriptive confidence.

The graph is shown before descriptive profile material. A faint daily signal and stronger adaptive
trend preserve detail without making multi-year windows unreadable.

The result language is deliberately observational: “higher during” or “lower during.” It does not
claim that the intervention caused the change.

## Preparing reconstructed history

Use the two templates:

- `examples/intervention-profiles-template.csv` for descriptions and expectations;
- `examples/intervention-periods-template.csv` for dated usage periods.

Review the profile file first. Add personal periods only after names, categories, dates, and
confidence labels have been checked.

## Page states

The interface supports:

- profile without dates;
- dates without a completed profile;
- dates that do not overlap Apple data;
- one period with multiple Apple outcomes;
- multiple periods for repeated within-person comparison.

No real intervention records are shipped with the repository.
