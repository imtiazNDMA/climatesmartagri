from pathlib import Path

from crop_disease.tracking import configure_mlflow


def test_mlflow_experiment_stores_artifacts_below_project_mlflow_directory(tmp_path):
    mlflow, _ = configure_mlflow(tmp_path, "manual")

    experiment = mlflow.get_experiment_by_name("manual")

    assert experiment is not None
    artifact_path = Path(experiment.artifact_location.removeprefix("file:///").replace("/", "\\"))
    assert artifact_path == tmp_path / ".mlflow" / "artifacts" / "manual"
