import dataclasses
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from seed_ops_store import seed  # noqa: E402

from csa_portal.ai.store import AiStore  # noqa: E402
from csa_portal.ai.tracing import Tracer  # noqa: E402
from csa_portal.main import create_app  # noqa: E402

TOKEN = "s3cret-ops-token"
HEADERS = {"X-Ops-Token": TOKEN}


@pytest.fixture
def ops(settings, tmp_path):
    store = AiStore(tmp_path / "ai.db")
    # The API reads the real clock, so seed around it; a fixed date drifts out of the metrics window.
    ids = seed(store, datetime.now(UTC))
    client = TestClient(create_app(dataclasses.replace(settings, ops_token=TOKEN), tracer=Tracer(store)))
    return client, ids


ROUTES = [
    "/api/ops/metrics", "/api/ops/eval-runs", "/api/ops/traces", "/api/ops/labels/queue", "/api/ops/calibration",
]


@pytest.mark.parametrize("path", ROUTES)
def test_every_route_needs_the_token(ops, path):
    client, _ = ops

    for headers in ({}, {"X-Ops-Token": "s3cret"}, {"X-Ops-Token": TOKEN + "x"}):
        response = client.get(path, headers=headers)
        assert response.status_code == 401, (path, headers)
        assert response.json()["detail"]["reason"] == "ops-unauthorized"
    assert client.get(path, headers=HEADERS).status_code == 200


def test_posting_a_label_needs_the_token_too(ops):
    client, ids = ops
    body = {"result_id": ids["results"]["b"]["case-b"], "labeller": "officer", "faithful": True}

    assert client.post("/api/ops/labels", json=body).status_code == 401
    created = client.post("/api/ops/labels", json=body, headers=HEADERS)
    assert created.status_code == 201 and len(created.json()["id"]) == 32


def test_without_a_token_setting_the_routes_do_not_exist(settings):
    client = TestClient(create_app(settings))

    assert client.get("/api/ops/metrics", headers=HEADERS).status_code == 404


def test_with_a_token_but_no_store_the_routes_say_so_after_checking_the_token(settings):
    client = TestClient(create_app(dataclasses.replace(settings, ops_token=TOKEN)))

    assert client.get("/api/ops/metrics").status_code == 401
    response = client.get("/api/ops/metrics", headers=HEADERS)
    assert (response.status_code, response.json()["detail"]["reason"]) == (503, "no-ai-store")


def test_metrics_choose_their_window_and_refuse_others(ops):
    client, _ = ops

    body = client.get("/api/ops/metrics?window=7d", headers=HEADERS).json()
    assert body["window"] == "7d" and body["live"]["requests"] >= 1
    assert client.get("/api/ops/metrics?window=1y", headers=HEADERS).status_code == 422


def test_compare_is_its_own_route_not_a_run_id(ops):
    client, ids = ops

    diff = client.get(f"/api/ops/eval-runs/compare?a={ids['runs']['a']}&b={ids['runs']['b']}", headers=HEADERS)

    assert diff.status_code == 200
    assert diff.json()["regressions"] == ["case-b"]


def test_compare_refuses_unknown_runs_and_different_datasets(ops):
    client, ids = ops

    unknown = client.get(f"/api/ops/eval-runs/compare?a={ids['runs']['a']}&b={'x' * 32}", headers=HEADERS)
    mixed = client.get(f"/api/ops/eval-runs/compare?a={ids['runs']['a']}&b={ids['runs']['c']}", headers=HEADERS)

    assert (unknown.status_code, unknown.json()["detail"]["reason"]) == (404, "unknown-run")
    assert (mixed.status_code, mixed.json()["detail"]["reason"]) == (422, "different-datasets")


def test_runs_and_traces_are_found_by_id_or_answer_404(ops):
    client, ids = ops

    assert client.get("/api/ops/eval-runs", headers=HEADERS).json()["runs"][0]["id"] == ids["runs"]["r"]
    assert client.get(f"/api/ops/eval-runs/{ids['runs']['b']}", headers=HEADERS).json()["run"]["dataset"] == "golden"
    assert client.get(f"/api/ops/eval-runs/{'x' * 32}", headers=HEADERS).json()["detail"]["reason"] == "unknown-run"
    page = client.get("/api/ops/traces?source=live&limit=2", headers=HEADERS).json()
    assert len(page["traces"]) == 2 and page["next"]
    following = client.get(f"/api/ops/traces?source=live&limit=2&before={page['next']}", headers=HEADERS).json()
    assert following["traces"][0]["id"] == ids["live"][2]
    trace = client.get(f"/api/ops/traces/{ids['live'][0]}", headers=HEADERS).json()
    assert [s["kind"] for s in trace["spans"]][:2] == ["agent", "llm"]
    missing = client.get(f"/api/ops/traces/{'x' * 32}", headers=HEADERS)
    assert (missing.status_code, missing.json()["detail"]["reason"]) == (404, "unknown-trace")


def test_labels_for_unknown_answers_or_out_of_range_are_refused_and_nothing_is_written(ops):
    client, ids = ops
    queue_before = client.get("/api/ops/labels/queue", headers=HEADERS).json()["queue"]

    unknown = client.post("/api/ops/labels", headers=HEADERS,
                          json={"result_id": "x" * 32, "labeller": "officer", "faithful": True})
    out_of_range = client.post("/api/ops/labels", headers=HEADERS,
                               json={"result_id": ids["results"]["b"]["case-b"], "labeller": "officer",
                                     "faithful": True, "helpful": 7})

    assert (unknown.status_code, unknown.json()["detail"]["reason"]) == (404, "unknown-result")
    assert out_of_range.status_code == 422
    assert client.get("/api/ops/labels/queue", headers=HEADERS).json()["queue"] == queue_before


def test_calibration_lists_each_judge(ops):
    client, _ = ops

    assert client.get("/api/ops/calibration", headers=HEADERS).json()["judges"][0]["judge_model"] == "gemma"


def test_the_token_setting_is_read_from_the_environment():
    from csa_portal.settings import Settings

    assert Settings._from({}).ops_token == ""
    assert Settings._from({"CSA_OPS_TOKEN": TOKEN}).ops_token == TOKEN
