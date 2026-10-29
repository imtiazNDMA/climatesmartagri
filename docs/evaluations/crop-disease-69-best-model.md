# Crop disease model: autoresearch result (#69)

- Generated: 2026-10-29
- Manifest: `f3e404e0…` (37 classes, 11,453 unique images; train/val/test 70/15/15)
- Registered: MLflow model `crop-disease` version 1, alias `candidate`, run `6207d21f6d8c408eaad9c07b69b55f15`, commit `1f188c9`
- Selection used validation macro F1 only. The locked test split was scored once, after selection.

## Result

| Model | Val macro F1 | Val accuracy | Test macro F1 | Test accuracy |
| --- | ---: | ---: | ---: | ---: |
| PyTorch MobileNetV2 baseline (#67) | 0.830 | 0.907 | 0.792 | 0.896 |
| **ConvNeXt-Nano + EMA, 25 epochs, seed 44** | **0.906** | **0.963** | **0.898** | **0.959** |

Test macro F1 rises by 0.106. The val-to-test drop is 0.008, so selecting on validation did not overfit it.

## Is the gain real?

The winner was retrained with three seeds under two schedules:

| Schedule | Seeds 42 / 43 / 44 | Mean ± SD | Range |
| --- | --- | --- | --- |
| 10-minute clock (as in the loop) | 0.888 / 0.872 / 0.896 | 0.885 ± 0.012 | 0.023 |
| **Fixed 25 epochs** | 0.898 / 0.895 / 0.906 | **0.900 ± 0.006** | **0.011** |

The gain over the baseline (+0.070 on val) is six times the seed range, so the acceptance criterion holds.

The loop's own best, 0.914, did not reproduce. Its learning-rate schedule followed the clock, so a busy GPU meant fewer, longer steps: that run fitted 27 epochs into ten minutes, while the re-runs on a free GPU fitted 47 and scored 0.872 to 0.904. Training now runs a fixed 25 epochs, with the ten minutes kept only as a safety cap.

![Autoresearch progress](crop-disease-autoresearch-progress.png)

## Which ideas helped

| Idea | Val macro F1 after |
| --- | ---: |
| Ten-minute MobileNetV2 baseline | 0.819 |
| 16 data loader workers (more epochs in the budget) | 0.833 |
| Full fine-tune, AdamW 1e-3, weight decay 0.05, warm-up then cosine | 0.876 |
| cuDNN autotuning | 0.888 |
| ConvNeXt-Nano backbone at 3e-4 | 0.898 |
| EMA of weights, decay 0.998 | 0.914 (0.900 over 3 seeds, fixed epochs) |

Did not help: label smoothing, EfficientNet-B0, drop path, 288 px images, mixup/cutmix, flip at test time, ConvNeXt-Tiny. Collapsed to F1 ≈ 0: learning rate 6e-4, and both DINOv3 ConvNeXt-Tiny attempts.

## Per crop (test macro F1)

| Crop | Classes | Baseline | New |
| --- | ---: | ---: | ---: |
| Cotton | 10 | 0.679 | 0.797 |
| Maize | 7 | 0.821 | 0.894 |
| Rice | 4 | 0.947 | 0.985 |
| Sugarcane | 5 | 0.903 | 0.980 |
| Wheat | 11 | 0.770 | 0.924 |

36 of 37 classes improve. The largest gains are cotton mealybug (+0.49), wheat healthy (+0.39) and wheat brown rust (+0.25).

Weakest classes, all small:

| Class | Test images | Test F1 |
| --- | ---: | ---: |
| Cotton anthracnose | 4 | 0.364 (baseline 0.444) |
| Cotton thrips | 5 | 0.364 |
| Maize fall armyworm | 16 | 0.706 |
| Maize stem borer | 14 | 0.741 |
| Cotton American bollworm | 8 | 0.750 |

Fall armyworm and the bollworm sit on the open taxonomy questions for Dr. Aamir (armyworm vs fall armyworm, the bollworm merge).

## What this does not answer

- **Field performance.** Every split comes from the same internet-sourced corpus. No Pakistan field images have been scored.
- **The historical Keras model** scored 0.904 val / 0.892 test in #67, but 91% of the clean val and test images were in its training folder, so those numbers are not comparable. It is not re-run, as the project uses PyTorch only.
- **`improved-002`**, the portal's rice and maize model, has not been scored on this split. It uses its own 39-class taxonomy and dataset, so a comparison needs a class mapping and an overlap check first.
- **Calibration.** Confidence values are uncalibrated; that is #70.
