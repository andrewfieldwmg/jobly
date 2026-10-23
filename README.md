# Jobly: source-independent decision-pipeline demo

Jobly is a publication-safe demonstration of a job-intelligence pipeline. It turns a noisy set of fictional vacancy records into a small, explainable human-review queue.

This repository contains only:

- a generic `JobSource` protocol;
- a synthetic fixture adapter and twelve fictional vacancies;
- canonical normalisation and conservative duplicate handling;
- deterministic eligibility gates for employment type, geography, freshness and compensation;
- transparent role-family scoring and explanations;
- a bounded human-review queue;
- a twelve-case golden set and eight regression tests.

It deliberately contains no source-specific collector, browser automation, copied vacancy text, account data, personal profile or CV data, credentials, application history, production database access, deployment configuration or operational logs.

## Run the demonstration

Python 3.11 or newer is recommended. There are no third-party runtime dependencies.

```powershell
python run_demo.py
python -m unittest test_demo.py -v
```

The run writes:

- `output/decision-surface.json` — the ranked queue, rejected records and explanations;
- `metrics/demo-evaluation.json` — the twelve expected-versus-observed golden cases.

## Pipeline

```text
JobSource
  -> canonical normalisation
  -> duplicate/repost collapse
  -> deterministic hard gates
  -> explainable scoring
  -> bounded human-review queue
  -> golden-case evaluation
```

The source boundary can be implemented by a documented API, a permitted employer feed, a public ATS interface used in accordance with its terms, or a fixture. Only the fixture implementation is distributed here.

## What the evaluation proves

The included fixture checks twelve deliberately constructed outcomes. A successful run demonstrates that the published rules execute reproducibly and that key edge cases remain covered by regression tests.

It does **not** establish real-world recommendation accuracy, employability, or suitability for hiring decisions. Jobly supports personal review; it does not submit applications or make decisions about candidates.
