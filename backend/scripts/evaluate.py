"""Evaluate the portal assistant on its datasets.

Recorded (default, what CI runs): replay each case's cassette, the model turns of a recorded live run.
    uv run python backend/scripts/evaluate.py --gate backend/evaluations/baseline.json
Live: ask the configured model, three times per case, and keep the run in the AI store.
    uv run python backend/scripts/evaluate.py --mode live --report docs/evaluations/assistant-live-baseline.md
Add --record to a live run to save its first repeat as the cassettes recorded runs replay.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from csa_portal.geoenv import use_bundled_proj  # noqa: E402

use_bundled_proj()

from csa_portal.ai.agents.assistant import AssistantService  # noqa: E402
from csa_portal.ai.evals.cassettes import CassetteModel, RecordingModel, cassette_path, load_cassette, save_cassette  # noqa: E402
from csa_portal.ai.evals.calibration import calibration  # noqa: E402
from csa_portal.ai.evals.judge import Judge  # noqa: E402
from csa_portal.ai.evals.datasets import DATASETS_DIR, load_dataset  # noqa: E402
from csa_portal.ai.evals.report import markdown_report  # noqa: E402
from csa_portal.ai.evals.runner import RunOutcome, run_dataset  # noqa: E402
from csa_portal.ai.model import LmStudioModel  # noqa: E402
from csa_portal.ai.store import AiStore  # noqa: E402
from csa_portal.ai.tracing import Tracer  # noqa: E402
from csa_portal.catalogue import load_catalogue  # noqa: E402
from csa_portal.facts import Facts  # noqa: E402
from csa_portal.forecast import ForecastService, load_registry  # noqa: E402
from csa_portal.hazard_models import DerivedService, load_hazard_models  # noqa: E402
from csa_portal.hazards import load_hazards  # noqa: E402
from csa_portal.main import _describe_forecast  # noqa: E402
from csa_portal.places import load_places  # noqa: E402
from csa_portal.sections import build_providers  # noqa: E402
from csa_portal.settings import BACKEND_DIR, Settings  # noqa: E402


def build_service(settings: Settings, model: Any, tracer: Tracer | None = None) -> AssistantService:
    catalogue = load_catalogue(settings.catalogue_path)
    places = load_places(settings.boundaries_dir)
    providers, _ = build_providers(settings.data_dir, settings.boundaries_dir)
    forecast = ForecastService(load_registry(settings.forecast_layers_path), None, settings.forecast_dir)
    derived = DerivedService(forecast, load_hazard_models(settings.hazard_models_path))
    return AssistantService(
        catalogue, places, Facts(catalogue, places, providers), model, settings.lm_studio_model,
        forecast_description=_describe_forecast(forecast, derived),
        hazard_description=load_hazards(settings.hazard_products_path).model_dump(mode="json"),
        local_model=True, tracer=tracer,
    )


def git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True, cwd=BACKEND_DIR
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return os.environ.get("GITHUB_SHA", "unknown")[:7] or "unknown"


# Pass rates are kept in baseline.json to this many decimals, and compared at the same precision.
BASELINE_DIGITS = 4


def gate(baseline: dict[str, float], outcomes: list[tuple[Any, RunOutcome]]) -> list[str]:
    """One message for each dataset whose pass rate is below its baseline."""
    messages = []
    for dataset, outcome in outcomes:
        expected = baseline.get(dataset.name)
        actual = outcome.record.summary["pass_rate"]
        if expected is not None and round(actual, BASELINE_DIGITS) < expected:
            messages.append(f"{dataset.name}: {actual:.1%} is below the baseline of {expected:.1%}")
    return messages


def judge_client(settings: Settings, name: str) -> LmStudioModel:
    """The judge's model on its LM Studio server, at temperature 0."""
    return LmStudioModel(settings.judge_url, name, settings.lm_studio_timeout, settings.lm_studio_api_key, temperature=0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", action="append", dest="datasets", help="golden, golden_ur, adversarial, ... (repeatable)")
    parser.add_argument("--mode", choices=("recorded", "live"), default="recorded")
    parser.add_argument("--repeats", type=int, help="runs per case (default 1 recorded, 3 live)")
    parser.add_argument("--record", action="store_true", help="live only: save the first repeat as cassettes")
    parser.add_argument("--case", action="append", dest="case_ids", help="run only this case id (repeatable)")
    parser.add_argument("--report", type=Path, help="write the markdown report here")
    parser.add_argument("--gate", type=Path, help="baseline.json: exit 1 when a dataset falls below it")
    parser.add_argument("--write-baseline", type=Path, help="write each dataset's pass rate here")
    parser.add_argument("--store", action=argparse.BooleanOptionalAction, help="keep the run in the AI store")
    parser.add_argument("--db", type=Path, help="the AI store (default: CSA_AI_DB)")
    parser.add_argument("--cassettes", type=Path, help="cassette directory (default: backend/evaluations/cassettes)")
    parser.add_argument("--judge", action="store_true", help="grade answers with the judge model")
    parser.add_argument("--judge-model", help="the judge's model id (default: CSA_JUDGE_MODEL)")
    args = parser.parse_args(argv)
    if args.record and args.mode != "live":
        parser.error("--record needs --mode live")

    settings = Settings.from_env()
    datasets = [load_dataset(name, DATASETS_DIR) for name in args.datasets or ["golden", "golden_ur", "adversarial"]]
    if args.case_ids:
        requested = set(args.case_ids)
        for dataset in datasets:
            dataset.cases = [case for case in dataset.cases if case.id in requested]
        found = {case.id for dataset in datasets for case in dataset.cases}
        if requested - found:
            parser.error("unknown case ids: " + ", ".join(sorted(requested - found)))

    keep = args.store if args.store is not None else args.mode == "live"
    db = args.db or settings.ai_db_path
    store = AiStore(db) if keep and db is not None else None
    cassettes = args.cassettes or DATASETS_DIR / "cassettes"
    if args.mode == "live":
        live = LmStudioModel(settings.lm_studio_url, settings.lm_studio_model, settings.lm_studio_timeout, settings.lm_studio_api_key)
        model: Any = RecordingModel(live) if args.record else live
        model_name = settings.lm_studio_model
    else:
        model = CassetteModel()
        model_name = "cassette-replay"
    service = build_service(settings, model, Tracer(store))
    repeats = args.repeats or (3 if args.mode == "live" else 1)

    judge, judge_gates = None, False
    if args.judge:
        name = args.judge_model or settings.judge_model
        if not name:
            parser.error("--judge needs --judge-model or CSA_JUDGE_MODEL")
        judge = Judge(judge_client(settings, name), name)
        state = calibration(store.calibration_pairs(name) if store is not None else [])
        judge_gates = state.calibrated
        kappa = "n/a" if state.kappa is None else f"{state.kappa:.2f}"
        print(f"Judge {name}: {state.labels} labels, {'calibrated' if judge_gates else 'uncalibrated'} (kappa {kappa})")

    outcomes = []
    for dataset in datasets:
        def before(case, repeat, name=dataset.name):
            if isinstance(model, CassetteModel):
                path = cassette_path(name, case.id, cassettes)
                model.load(load_cassette(path) if path.exists() else None)
            elif isinstance(model, RecordingModel) and repeat == 0:
                model.start()

        def after(case, repeat, name=dataset.name):
            if isinstance(model, RecordingModel) and repeat == 0:
                save_cassette(cassette_path(name, case.id, cassettes), model.turns)

        outcome = run_dataset(
            service, dataset, mode=args.mode, model=model_name, repeats=repeats, git_sha=git_sha(),
            before_case=before, after_case=after, store=store, judge=judge, judge_gates=judge_gates,
        )
        outcomes.append((dataset, outcome))
        summary = outcome.record.summary
        print(f"{dataset.name}: {summary['passed_cases']}/{summary['cases']} passed every repeat "
              f"({summary['pass_rate']:.1%}); flaky: {', '.join(summary['flaky_cases']) or 'none'}")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(markdown_report(outcomes), encoding="utf-8", newline="\n")
        print(f"Report: {args.report}")
    if args.write_baseline:
        rates = {dataset.name: round(outcome.record.summary["pass_rate"], BASELINE_DIGITS) for dataset, outcome in outcomes}
        args.write_baseline.write_text(json.dumps(rates, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"Baseline: {args.write_baseline}")
    if args.gate:
        failures = gate(json.loads(args.gate.read_text(encoding="utf-8")), outcomes)
        for message in failures:
            print(message)
        if failures:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
