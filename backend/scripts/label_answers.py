"""Label evaluated answers by hand, so the judge can be calibrated against people.

    uv run python backend/scripts/label_answers.py --labeller "Your name" --judge-model google/gemma-4-26b-a4b

For each answer: is every factual claim right (y/n), how helpful is it (1-5, or Enter to skip), and an optional
note. s skips an answer, q stops. The AI Ops dashboard (#33) will offer the same in the browser.
"""

from __future__ import annotations

import argparse
import secrets
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from csa_portal.ai.evals.calibration import calibration  # noqa: E402
from csa_portal.ai.store import AiStore, LabelRecord  # noqa: E402
from csa_portal.settings import Settings  # noqa: E402


def _choice(ask: Callable[[str], str], say: Callable[[str], None], prompt: str, allowed: set[str]) -> str:
    while True:
        answer = ask(prompt).strip().lower()
        if answer in allowed:
            return answer
        say(f"Please answer one of: {', '.join(sorted(a or 'Enter' for a in allowed))}")


def main(argv: list[str] | None = None, ask: Callable[[str], str] = input, say: Callable[[str], None] = print) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--labeller", required=True, help="your name, kept with each label")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--db", type=Path, help="the AI store (default: CSA_AI_DB)")
    parser.add_argument("--judge-model", help="show this judge's calibration at the end")
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    db = args.db or settings.ai_db_path
    if db is None:
        parser.error("no AI store: set CSA_AI_DB or pass --db")
    store = AiStore(db)

    pending = store.unlabelled_results(args.limit)
    if not pending:
        say("Nothing to label. Run a live evaluation (npm run eval:live) first.")
        return 0
    for index, result in enumerate(pending, 1):
        say(f"\n[{index}/{len(pending)}] {result.case_id}\nQuestion: {result.question}\nAnswer: {result.answer}")
        faithful = _choice(ask, say, "Is every factual claim right? (y/n, s skip, q quit) ", {"y", "n", "s", "q"})
        if faithful == "q":
            break
        if faithful == "s":
            continue
        helpful = _choice(ask, say, "How helpful, 1-5? (Enter to skip) ", {"1", "2", "3", "4", "5", ""})
        note = ask("Note (optional): ").strip()
        store.write_label(LabelRecord(
            secrets.token_hex(16), result.result_id, args.labeller, faithful == "y",
            int(helpful) if helpful else None, note, datetime.now(UTC),
        ))
    name = args.judge_model or settings.judge_model
    if name:
        state = calibration(store.calibration_pairs(name))
        kappa = "n/a" if state.kappa is None else f"{state.kappa:.2f}"
        say(f"Judge {name}: {state.labels} labels, {'calibrated' if state.calibrated else 'uncalibrated'} (kappa {kappa})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
