"""Fill each case's fact_values with every number the assistant is shown for it, from the real portal data.

Run after changing a case's view or expected tools, or after the portal's data changes:
    uv run python backend/scripts/fill_eval_facts.py
Numbers already listed by hand are kept. Every case is filled: an answer that declines a request may still
quote what the portal holds, and that is grounded; forbidden_values still fail it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from csa_portal.geoenv import use_bundled_proj  # noqa: E402

use_bundled_proj()

from csa_portal.ai.evals.datasets import dataset_path, dump_dataset, load_dataset  # noqa: E402
from csa_portal.ai.evals.grounding import shown_numbers  # noqa: E402
from csa_portal.ai.model import ScriptedModel  # noqa: E402
from csa_portal.settings import Settings  # noqa: E402
from evaluate import build_service  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", action="append", dest="datasets")
    args = parser.parse_args()
    service = build_service(Settings.from_env(), ScriptedModel([]))
    for name in args.datasets or ["golden", "adversarial"]:
        dataset = load_dataset(name)
        for case in dataset.cases:
            case.fact_values = sorted(set(case.fact_values) | set(shown_numbers(service, case)))
        dataset_path(name).write_text(dump_dataset(dataset), encoding="utf-8", newline="\n")
        print(f"{name}: filled {len(dataset.cases)} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
