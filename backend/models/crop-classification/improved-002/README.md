# Crop classifier improved-002

Runtime package for the portal's Rice and Maize image classifier.

- `model.ts`: frozen TorchScript model used for inference.
- `label_map.json`: stable class IDs and display labels.
- `portal_inference.py`: preprocessing and model invocation contract.
- `inference_config.json`: machine-readable input and output contract.
- `model_manifest.json`: source artifact checksums and training metadata.
- `evaluation_summary.json`: internal holdout metrics.

The retraining bundle and sample images are intentionally omitted. Install the optional runtime with `uv sync --group ml`.

This classifier is an initial screening tool, not a pesticide recommendation or replacement for field diagnosis.
