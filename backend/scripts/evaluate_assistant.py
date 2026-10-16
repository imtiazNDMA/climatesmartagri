"""Run the assistant golden set in recorded mode or against the configured live model."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from csa_portal.geoenv import use_bundled_proj  # noqa: E402

use_bundled_proj()

from csa_portal.assistant import AssistantChatRequest, AssistantService, AssistantView  # noqa: E402
from csa_portal.catalogue import load_catalogue  # noqa: E402
from csa_portal.evaluation import load_golden_set, markdown_report, score_answer  # noqa: E402
from csa_portal.facts import Facts  # noqa: E402
from csa_portal.forecast import ForecastService, load_registry  # noqa: E402
from csa_portal.hazard_models import DerivedService, load_hazard_models  # noqa: E402
from csa_portal.hazards import load_hazards  # noqa: E402
from csa_portal.language_model import Completion, LmStudioModel, ScriptedModel  # noqa: E402
from csa_portal.language_model import ModelError  # noqa: E402
from csa_portal.main import _describe_forecast  # noqa: E402
from csa_portal.places import load_places  # noqa: E402
from csa_portal.sections import build_providers  # noqa: E402
from csa_portal.settings import BACKEND_DIR, Settings  # noqa: E402


def build_service(settings: Settings, answers: list[str] | None = None) -> AssistantService:
    catalogue = load_catalogue(settings.catalogue_path)
    places = load_places(settings.boundaries_dir)
    providers, _ = build_providers(settings.data_dir, settings.boundaries_dir)
    forecast = ForecastService(load_registry(settings.forecast_layers_path), None, settings.forecast_dir)
    derived = DerivedService(forecast, load_hazard_models(settings.hazard_models_path))
    model = (
        ScriptedModel([Completion(text=answer) for answer in answers])
        if answers is not None
        else LmStudioModel(settings.lm_studio_url, settings.lm_studio_model, settings.lm_studio_timeout, settings.lm_studio_api_key)
    )
    return AssistantService(
        catalogue,
        places,
        Facts(catalogue, places, providers),
        model,
        "scripted-recording" if answers is not None else settings.lm_studio_model,
        forecast_description=_describe_forecast(forecast, derived),
        hazard_description=load_hazards(settings.hazard_products_path).model_dump(mode="json"),
        local_model=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("recorded", "live"), default="recorded")
    parser.add_argument("--golden", type=Path, default=BACKEND_DIR / "evaluations" / "assistant_golden.json")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--case", action="append", dest="case_ids", help="Run only this case id; repeat as needed")
    args = parser.parse_args()

    golden = load_golden_set(args.golden)
    if args.case_ids:
        requested = set(args.case_ids)
        golden.cases = [case for case in golden.cases if case.id in requested]
        missing = requested - {case.id for case in golden.cases}
        if missing:
            parser.error("unknown case ids: " + ", ".join(sorted(missing)))
    recorded = [case.recorded_answer for case in golden.cases] if args.mode == "recorded" else None
    settings = Settings.from_env()
    service = build_service(settings, recorded)
    scores = []
    for case in golden.cases:
        started = time.perf_counter()
        tool_calls = 0
        result: dict = {}
        try:
            result = service.answer(
                AssistantChatRequest(question=case.question, view=AssistantView.model_validate(case.view.model_dump()))
            )
            answer = result["answer"]
            tool_calls = result.get("tool_calls", 0)
        except ModelError as error:
            answer = f"Evaluation error: {error.reason}: {error.message}"
        scores.append(score_answer(case, answer, time.perf_counter() - started, tool_calls))
        print(f"{case.id}: {'pass' if scores[-1].passed else 'FAIL'} ({scores[-1].latency_seconds:.2f}s)")

    model = "scripted-recording" if args.mode == "recorded" else settings.lm_studio_model
    report = markdown_report(golden, scores, model, args.mode, datetime.now(UTC).isoformat(timespec="seconds"))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report, encoding="utf-8")
        print(f"Report: {args.report}")
    print(f"Passed {sum(score.passed for score in scores)}/{len(scores)}")
    return 0 if all(score.passed for score in scores) else 1


if __name__ == "__main__":
    raise SystemExit(main())
