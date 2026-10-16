"""The language model seam lives in csa_portal.ai.model; the old path hands out the same objects for one release."""


def test_the_old_seam_path_is_the_same_seam():
    from csa_portal import language_model
    from csa_portal.ai import model

    for name in ("Completion", "LanguageModel", "LmStudioModel", "ModelError", "ScriptedModel", "Tool", "ToolCall"):
        assert getattr(language_model, name) is getattr(model, name), name
