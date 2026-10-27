# Crop disease autoresearch program

Improve validation macro F1 within a fixed ten-minute RTX 6000 training budget.

## Fixed boundary

- Do not edit `prepare.py`, `run.py`, the manifest, taxonomy or tests.
- Edit only `autoresearch/train.py`.
- Do not add dependencies.
- Test images are unavailable by design. Never modify imports or paths to reach them.
- The score is validation macro F1. Memory is peak allocated CUDA memory.

## Start

1. Choose a short tag and create `autoresearch/<tag>` from the current accepted commit.
2. Set `CSA_CROP_DATA_DIR` to the external `dataset_filtered` folder.
3. Record the current best validation macro F1 from `results.tsv` or use `0.8304` for the initial baseline.

## One experiment

1. Change one coherent idea in `train.py`. Architecture (`timm` only), resolution, augmentation, optimiser, schedule, loss and sampling are fair game.
2. Prefer the simplest change that could explain an improvement. Complexity needs a measurable payoff.
3. Commit the candidate before running it.
4. Run from `ml/crop-disease/autoresearch`:

   ```powershell
   uv run python -m autoresearch.run --commit <sha> --description "<idea>" --baseline <best-score>
   ```

   The runner executes `uv run train.py`, captures `run.log`, kills runs after 20 minutes, writes `results.tsv`, and logs the same status and metrics to MLflow.
5. Read the final `val_macro_f1:` and `peak_vram_mb:` lines plus `run.log`.
6. If macro F1 improved, keep the commit and use the new score as the baseline.
7. If it did not improve or crashed, the runner resets the candidate commit. Confirm `git status` before continuing.

## Results

`results.tsv` is local and uncommitted:

```text
commit  val_macro_f1  memory_gb  status  description
```

Statuses are `keep`, `discard` and `crash`. Every row must have a corresponding MLflow `autoresearch` run tagged with the same commit, status and description.
