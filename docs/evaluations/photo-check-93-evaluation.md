# Photo check evaluation (#93)

Whether the vision model may name the crop in a reader's photo (Auto), measured against the bars in PRD #90. Model: `qwen/qwen3.8-27b` on LM Studio, temperature 0, no training. Run on 2026-11-11.

**Result: do not ship Auto.** It stays switched off (`CSA_PHOTO_CHECK` unset). The photo check can still stop non-plants and warn about poor photos; neither is wired into the panel yet.

## The set

1,400 photos in two parts of 700, chosen with a fixed seed (`backend/scripts/build_photo_check_set.py`). The manifest is in git; the photos are not, since they come from public datasets and the crop disease corpus. Every photo is named by the SHA-256 of its file.

| Group | Per part | Source |
| --- | --- | --- |
| Five-crop leaves | 500 (100 per crop) | the crop disease manifest: `tune` from the val split, `final` from the locked test split |
| Other plants | 100 | PlantVillage test split (BrandonFors mirror), maize left out; 42 of the 100 are tomato |
| Not plants | 50 | Imagenette, ten kinds of object and animal |
| Poor photos | 50 | spare val photos, degraded by script: Gaussian blur, brightness cut to 12%, or a 12x downscale and back |

The prompt was worked on with `tune` only. It was frozen, then `final` was scored once.

## Bars and results

| Bar | Needed | Tune, round 1 | Tune, round 2 | Tune, round 3 (frozen) | **Final** | Met |
| --- | --- | --- | --- | --- | --- | --- |
| Crop identification, five crops | at least 97% | 61.0% | 58.0% | 55.0% | **51.2%** | no |
| False stops (a crop photo refused) | at most 2% | 0.8% | 10.2% | 6.8% | **6.2%** | no |
| Non-plant stopped | at least 95% | 100% | 100% | 100% | **100%** | yes |
| Other plant stopped | at least 85% | 30.0% | 97.0% | 88.0% | **91.0%** | yes |
| Classifier macro F1 through Auto, drop from hand-picked | at most 0.02 | 0.061 | 0.169 | 0.121 | **0.112** | no |
| Quality warning on degraded photos | reported only | 38% | 96% | 94% | **96%** | |
| Quality warning on clean photos | reported only | 41% | 23% | 12% | **13%** | |

Classifier macro F1 on the final five-crop sample: 0.915 when the crop is hand-picked, 0.803 through Auto. (This is the sample's score, not the 0.898 of the whole locked test split.)

"Crop identification" counts a photo as right only when Auto names the true crop. A photo Auto hands back to the reader ("unclear") is not wrong, since the reader then names the crop, but it is not identified either.

### Final part, by crop

| Crop | Right | Wrong crop | Unclear | Refused |
| --- | --- | --- | --- | --- |
| Cotton | 62 | 2 | 12 | 24 |
| Maize | 42 | 12 | 44 | 2 |
| Rice | 45 | 8 | 47 | 0 |
| Sugarcane | 76 | 5 | 19 | 0 |
| Wheat | 31 | 17 | 47 | 5 |

Wrong-crop answers: Maize to Sugarcane (11), Wheat to Maize (9), Rice to Maize (7), Wheat to Rice (5), Sugarcane to Maize (4), Wheat to Sugarcane (3), and 1 to 2 each for six other pairs.

## What the rounds show

- **Cotton against other broad leaves is a trade-off a prompt cannot settle.** Round 1 described cotton as a broad leaf and the model called 37 of 42 tomato leaves cotton (unsupported plants stopped: 30%). Spelling out the cotton leaf shape in round 2 fixed that, and the model then refused a third of real cotton as another plant. Round 3 sends doubtful broad leaves to "unclear" instead, which cut the cotton refusals only to 24 of 100.
- **The four grass crops stay uncertain.** Rice, maize and wheat are "unclear" for 44 to 47 photos in 100, mostly healthy leaves and tight close-ups of one blade, where a person could not name the crop either. When the model does name one, it mixes them up (wheat for maize, maize for sugarcane).
- **Stopping non-plants and warning on poor photos work.** All 50 non-plants were stopped; 96% of degraded photos raised a warning, with 13% false alarms on clean photos.
- **Round 3 was chosen over round 1** even though round 1 scores higher on crop identification, because round 1 let 70 of 100 other plants through as cotton or another crop. A 61% that classifies tomato leaves as cotton is not a better photo check.

## Limits

- The five-crop photos come from the public datasets the classifier trained on, each crop from different sources with their own backgrounds and cameras. The score says little about Pakistan field photos (#18).
- The other-plant photos are 42% tomato, and the 91% is mostly the model recognising tomato leaves.
- Degraded photos are made by script, a rough stand-in for real bad photos. Quality warnings are reported, not gating, for that reason.
- One run at temperature 0, so no measure of run-to-run variation. About 80 to 90 photos per crop in the final part (100 sampled) are too few to separate crops that differ by a few points.
- Three prompt rounds were tried on the tuning part; the final part was scored once, after the prompt was frozen.
- Two photos in the set carry malformed EXIF, which made `Photo.from_upload` fail; it was fixed in this branch (it only reads the orientation tag now).

## Decision

Auto ships switched off, as agreed in the grilling. Crop identification is 51% against 97%, and tuning the prompt did not move it: the three rounds ranged from 55% to 61% on the tuning part. The next candidate for the photo check is a fine-tuned vision model (#100), scored on this same set.

## Reproducing

```
uv run --with pyarrow python backend/scripts/build_photo_check_set.py      # photos; needs CSA_CROP_DATA_DIR and a download
uv run python backend/scripts/evaluate_photo_check.py --part tune          # ask the model, record, report
uv run python backend/scripts/evaluate_photo_check.py --part final --shipping
uv run python backend/scripts/evaluate_photo_check.py --part final --recorded   # report from the recording, no model
```

The answers are recorded in `backend/evaluations/photo_check/readings/`. CI replays them (`test_photo_check_eval.py`) and fails if the prompt changes after its final evaluation or a recording no longer gives its committed report.
