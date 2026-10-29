from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from urllib.parse import quote


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_commit(project: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=project, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def configure_mlflow(project: Path, experiment: str):
    import mlflow

    store = project / ".mlflow"
    store.mkdir(parents=True, exist_ok=True)
    tracking_uri = f"sqlite:///{quote((store / 'mlflow.db').as_posix(), safe='/:')}"
    mlflow.set_tracking_uri(tracking_uri)
    artifact_location = (store / "artifacts" / experiment).as_uri()
    try:
        mlflow.create_experiment(experiment, artifact_location=artifact_location)
    except mlflow.exceptions.MlflowException as error:
        if "already exists" not in str(error):
            raise
    mlflow.set_experiment(experiment)
    configured = mlflow.get_experiment_by_name(experiment)
    if configured is None or configured.artifact_location != artifact_location:
        raise RuntimeError(
            f"MLflow experiment {experiment!r} uses {getattr(configured, 'artifact_location', None)!r}; "
            f"delete the local .mlflow store to recreate it at {artifact_location!r}"
        )
    return mlflow, tracking_uri
