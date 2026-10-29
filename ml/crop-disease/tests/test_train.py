from torch import nn

from train import build_model, set_backbone_trainable


class TinyModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(nn.Linear(2, 2), nn.Linear(2, 2), nn.Linear(2, 2))
        self.classifier = nn.Linear(2, 2)

    def get_classifier(self):
        return self.classifier


def test_head_phase_freezes_backbone_and_keeps_classifier_trainable():
    model = TinyModel()

    set_backbone_trainable(model, trainable=False, fine_tune_layers=1)

    assert not any(parameter.requires_grad for parameter in model.features.parameters())
    assert all(parameter.requires_grad for parameter in model.classifier.parameters())


def test_fine_tuning_unfreezes_only_the_last_backbone_modules():
    model = TinyModel()

    set_backbone_trainable(model, trainable=True, fine_tune_layers=1)

    assert not any(parameter.requires_grad for parameter in model.features[:2].parameters())
    assert all(parameter.requires_grad for parameter in model.features[2:].parameters())
    assert all(parameter.requires_grad for parameter in model.classifier.parameters())


def test_historical_classifier_head_has_dense_relu_dropout_and_output(monkeypatch):
    backbone = TinyModel()
    backbone.num_features = 2
    called = {}

    def create_model(*args, **kwargs):
        called.update(kwargs)
        return backbone

    monkeypatch.setattr("train.timm.create_model", create_model)

    model = build_model("mobilenetv2_100", num_classes=7)

    assert [type(layer) for layer in model.classifier] == [nn.Linear, nn.ReLU, nn.Dropout, nn.Linear]
    assert model.classifier[0].out_features == 256
    assert model.classifier[2].p == 0.4
    assert model.classifier[3].out_features == 7
    assert called == {"pretrained": True, "num_classes": 0}
