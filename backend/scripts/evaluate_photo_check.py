"""Run the photo check's evaluation (#93) and say whether Auto meets its bars.

    uv run python backend/scripts/evaluate_photo_check.py --part tune            # ask the model, record, report
    uv run python backend/scripts/evaluate_photo_check.py --part final --shipping
    uv run python backend/scripts/evaluate_photo_check.py --part tune --recorded # report from the recording only

A live run needs LM Studio and the photos (`build_photo_check_set.py`). It records each answer by the photo's
hash in `backend/evaluations/photo_check/readings/<model>-<part>.json`, saving as it goes, and picks up where an
interrupted run stopped. Answers recorded under a different prompt are thrown away for `tune`; for `final`, which
is scored once, the run stops and says so unless `--again` is given.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from csa_portal.ai.evals.photo_check import (  # noqa: E402
    EVALUATION_DIR, Case, RecordedRun, Report, load_cases, load_readings, prompt_sha256, save_readings, score,
)
from csa_portal.ai.model import LmStudioModel, ModelError, Photo  # noqa: E402
from csa_portal.photo_check import PhotoCheck  # noqa: E402
from csa_portal.settings import Settings  # noqa: E402

CROP_PROJECT = BACKEND.parent / "ml" / "crop-disease"
DEFAULT_CROP_DATA = BACKEND.parent / "Aamir Ai  Project" / "Crop Disease Detection" / "dataset_filtered"
# The crop disease model's own answers with the true crop given, from its final run: val for tune, test for final.
HAND_PREDICTIONS = {"tune": "val", "final": "test"}


def photo_path(case: Case, crop_data: Path) -> Path:
    return crop_data / case.path if case.source in {"val", "test"} else EVALUATION_DIR / "images" / case.path


def hand_predictions(part: str) -> dict[str, str]:
    path = CROP_PROJECT / "runs" / "final-seed44" / HAND_PREDICTIONS[part] / "predictions.csv"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8", newline="") as file:
        return {row["path"]: row["predicted"] for row in csv.DictReader(file)}


def render(report: Report, title: str) -> str:
    lines = [title, "", "| Bar | Score | Needed | Met |", "| --- | --- | --- | --- |"]
    for bar in report.bars:
        needed = f"{'at least' if bar.at_least else 'at most'} {bar.threshold:.0%}"
        if bar.name == "auto-macro-f1-drop":
            lines.append(f"| {bar.name} | {bar.value:.3f} | at most {bar.threshold:.2f} | {'yes' if bar.met else 'no'} |")
        else:
            lines.append(f"| {bar.name} | {bar.value:.1%} | {needed} | {'yes' if bar.met else 'no'} |")
    lines += ["", f"Auto: {'ship' if report.ship else 'do not ship'}", "", "| Crop | Right | Wrong crop | Unclear | Stopped |",
              "| --- | --- | --- | --- | --- |"]
    for crop, counts in sorted(report.crop_outcomes.items()):
        lines.append(f"| {crop} | {counts['right']} | {counts['wrong-crop']} | {counts['unclear']} | {counts['stopped']} |")
    lines += ["", "Wrong-crop answers: " + (", ".join(f"{pair} ({n})" for pair, n in report.confusions.items()) or "none")]
    if report.hand_macro_f1 is not None:
        lines.append(f"Classifier macro F1: {report.hand_macro_f1:.3f} hand-picked, {report.auto_macro_f1:.3f} through Auto")
    if report.quality_raised_on_poor is not None:
        lines.append(
            f"Quality warning raised on {report.quality_raised_on_poor:.0%} of degraded photos "
            f"and {report.quality_raised_on_clean:.0%} of clean five-crop photos"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--part", choices=["tune", "final"], required=True)
    parser.add_argument("--model", default=settings.lm_studio_model)
    parser.add_argument("--url", default=settings.lm_studio_url)
    parser.add_argument("--recorded", action="store_true", help="score the recording; ask the model nothing")
    parser.add_argument("--shipping", action="store_true", help="mark this run as the one the portal's prompt rests on")
    parser.add_argument("--again", action="store_true", help="re-score the final part under a changed prompt")
    parser.add_argument("--limit", type=int, help="only the first N photos, for a quick look (nothing is recorded)")
    args = parser.parse_args()

    cases = [case for case in load_cases() if case.part == args.part]
    if not cases:
        sys.exit("The evaluation set is not built: run backend/scripts/build_photo_check_set.py")
    path = EVALUATION_DIR / "readings" / f"{args.model.replace('/', '-')}-{args.part}.json"
    run = load_readings(path) if path.is_file() else RecordedRun(args.model, prompt_sha256(), {})

    if not args.recorded:
        if run.prompt_sha256 != prompt_sha256():
            if args.part == "final" and not args.again:
                sys.exit("The final part was already scored under another prompt. It is scored once; pass --again to redo it.")
            run = RecordedRun(args.model, prompt_sha256(), {})
        crop_data = Path(os.environ.get("CSA_CROP_DATA_DIR", DEFAULT_CROP_DATA))
        check = PhotoCheck(LmStudioModel(args.url, args.model, timeout=120, temperature=0), args.model)
        todo = [case for case in cases if case.id not in run.readings][: args.limit]
        started = time.perf_counter()
        for number, case in enumerate(todo, 1):
            photo = Photo.from_upload(photo_path(case, crop_data).read_bytes())
            for attempt in range(4):
                try:
                    run.readings[case.id] = check.read(photo)
                    break
                except ModelError as err:
                    # LM Studio drops a request now and then in a long run; a real outage still stops it.
                    if attempt == 3:
                        save_readings(path, run) if not args.limit else None
                        sys.exit(f"Stopped at photo {number} of {len(todo)} ({err.reason}): {err.message}. Run again to go on.")
                    time.sleep(20)
            if number % 25 == 0 or number == len(todo):
                if not args.limit:
                    save_readings(path, run)
                print(f"{number}/{len(todo)} photos, {time.perf_counter() - started:.0f}s", flush=True)
        if args.limit:
            cases = [case for case in cases if case.id in run.readings]

    run.hand_predictions = hand_predictions(args.part)
    run.shipping = run.shipping or args.shipping
    report = score(cases, run.readings, run.hand_predictions)
    if not args.limit:
        # Only the predictions the report used are kept beside the answers, so CI can replay it.
        used = {case.path for case in cases}
        run.hand_predictions = {key: value for key, value in run.hand_predictions.items() if key in used}
        save_readings(path, run)
        path.with_suffix(".report.json").write_text(report.to_json(), encoding="utf-8", newline="\n")
    print(render(report, f"Photo check, {args.part} part, {args.model}, {sum(report.photos.values())} photos"))


if __name__ == "__main__":
    main()
