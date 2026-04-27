from __future__ import annotations

from meta_writing.prompt_profiles import detect_prompt_profile


def test_detect_prompt_profile_defaults_to_generic() -> None:
    profile = detect_prompt_profile("", "")

    assert profile.key == "generic"
    assert profile.third_editor_enabled is True
    assert profile.third_editor_mode == "story"


def test_detect_prompt_profile_recognizes_tomato_projects() -> None:
    profile = detect_prompt_profile(
        creator_guidance="平台风格：番茄女频，高梗密度，快节奏，系统向，强情绪拉扯",
        target_satisfaction_type="打脸、反转、关系推进",
    )

    assert profile.key == "tomato_romance"
    assert profile.third_editor_enabled is True
    assert profile.third_editor_mode == "story"


def test_detect_prompt_profile_recognizes_literary_microfeel_projects() -> None:
    profile = detect_prompt_profile(
        creator_guidance="核心审美：克制美学，强调微感、留白和不解释",
        target_satisfaction_type="克制美学",
    )

    assert profile.key == "literary_microfeel"
    assert profile.third_editor_enabled is True
    assert profile.third_editor_mode == "literary_theme"
