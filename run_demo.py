from __future__ import annotations

import argparse
import json
from pathlib import Path

from jobly_demo import FixtureSource, evaluate_expected, run_pipeline


ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the publication-safe Jobly demonstration.")
    parser.add_argument("--input", type=Path, default=ROOT / "fixtures" / "jobs.json")
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "decision-surface.json")
    parser.add_argument("--metrics", type=Path, default=ROOT / "metrics" / "demo-evaluation.json")
    args = parser.parse_args()

    source = FixtureSource(args.input)
    result = run_pipeline(source)
    evaluation = evaluate_expected(result, source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.metrics.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    args.metrics.write_text(json.dumps(evaluation, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "summary": result["summary"],
                "evaluation": {key: evaluation[key] for key in ("cases", "passed", "failed")},
            }
        )
    )


if __name__ == "__main__":
    main()
