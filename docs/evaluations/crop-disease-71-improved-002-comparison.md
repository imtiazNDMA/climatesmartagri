# Rice and maize: new model vs `improved-002` (#71)

- Generated: 2026-10-29
- New model: MLflow `crop-disease` v1 (`candidate`), ConvNeXt-Nano, seed 44
- `improved-002`: the portal's rice and maize TorchScript package
- Script: `ml/crop-disease/compare_improved_002.py`

## Which images

Both models learned from the same public rice and maize datasets (the filenames match, e.g. `TUNGRO1_214.JPG`, `Corn_Gray_Spot (545).JPG`), so most of our held-out images may be in `improved-002`'s training set. Its training images are not on this PC, so images are matched by original filename. An image counts when:

- it is in `improved-002`'s strict test split and in our val or test split
- its filename is not generic (`00000001.jpg` recurs across datasets)
- both datasets give it the same class

About 15% of our rice and maize images match, the same share as `improved-002`'s test split. The matches are not hash-verified.

Only the 7 disease and healthy classes below matched. No pest images matched, so pests are not compared. `improved-002` is told the crop; the new model chose among all 37 classes.

## Result (macro F1 over the shared classes)

| Split | Images | `improved-002` | New model |
| --- | ---: | ---: | ---: |
| Our test: rice | 62 | 0.971 | 1.000 |
| Our test: maize | 78 | 0.956 | 0.985 |
| **Our test: both** | **140** | **0.964** | **0.993** |
| Our val: both | 131 | 0.945 | 0.994 |

## Decision

The new model wins on the shared classes, but it covers far less of rice and maize:

| | `improved-002` | New model |
| --- | ---: | ---: |
| Rice classes | 24 (6 diseases, healthy, 17 pests) | 4 diseases, no healthy class |
| Maize classes | 15 | 7 |

Replacing `improved-002` would label every healthy rice leaf as a disease and lose rice pests and most maize pests. The rule in #71 did not foresee this, so the user decided on 2026-10-29: **rice and maize stay on `improved-002`; the new model serves cotton, wheat and sugarcane.**
