from pathlib import Path

from PIL import Image

from crop_disease.dataset import ManifestDataset, read_dataset_index


def test_dataset_index_uses_only_kept_rows_in_the_requested_split(tmp_path):
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "path,source_split,source_label,label,crop,category,sha256,dhash,group,status,split\n"
        "Train/A/a.jpg,Train,A,rust,Wheat,disease,a,00,g1,kept,train\n"
        "Train/A/a-copy.jpg,Train,A,rust,Wheat,disease,a,00,g1,duplicate,train\n"
        "Validation/B/b.jpg,Validation,B,healthy,Wheat,healthy,b,11,g2,kept,val\n",
        encoding="utf-8",
    )

    index = read_dataset_index(manifest, "train")

    assert index.class_names == ("healthy", "rust")
    assert index.present_classes == frozenset({"rust"})
    assert [(item.path, item.target) for item in index.items] == [("Train/A/a.jpg", 1)]


def test_manifest_dataset_loads_rgb_images_and_applies_transform(tmp_path):
    image_path = tmp_path / "Train/A/a.png"
    image_path.parent.mkdir(parents=True)
    Image.new("L", (5, 4), 128).save(image_path)
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "path,source_split,source_label,label,crop,category,sha256,dhash,group,status,split\n"
        "Train/A/a.png,Train,A,rust,Wheat,disease,a,00,g1,kept,train\n",
        encoding="utf-8",
    )

    dataset = ManifestDataset(tmp_path, read_dataset_index(manifest, "train"), lambda image: image.mode)

    assert dataset[0] == ("RGB", 0)
