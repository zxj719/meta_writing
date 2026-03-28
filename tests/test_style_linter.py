# -*- coding: utf-8 -*-
"""Tests for the style linter."""

import pytest
from meta_writing.style_linter import StyleLinter, Severity


@pytest.fixture
def linter():
    return StyleLinter()


class TestObjectRemembers:
    def test_catches_object_remembers(self, linter):
        text = "沙发记得他按下去的弧度。"
        issues = linter.check(text)
        errors = [i for i in issues if i.pattern_name == "object_remembers"]
        assert len(errors) == 1
        assert errors[0].severity == Severity.ERROR

    def test_catches_various_objects(self, linter):
        for obj in ["门框", "铁皮", "木头", "砚台", "墙壁"]:
            text = f"{obj}记得那些声音。"
            issues = linter.check(text)
            errors = [i for i in issues if i.pattern_name == "object_remembers"]
            assert len(errors) >= 1, f"Should catch {obj}记得"

    def test_allows_person_remembers(self, linter):
        text = "她记得小时候的事。"
        issues = linter.check(text)
        errors = [i for i in issues if i.pattern_name == "object_remembers"]
        assert len(errors) == 0


class TestGenericRemembers:
    def test_catches_it_remembers(self, linter):
        text = "它记得每一次被打开的温度。"
        issues = linter.check(text)
        errors = [i for i in issues if i.pattern_name == "generic_remembers"]
        assert len(errors) == 1

    def test_catches_them_remembers(self, linter):
        text = "它们记得所有的脚步声。"
        issues = linter.check(text)
        errors = [i for i in issues if i.pattern_name == "generic_remembers"]
        assert len(errors) == 1


class TestObjectSpeaking:
    def test_catches_object_speaking(self, linter):
        text = "沙发在说话。"
        issues = linter.check(text)
        errors = [i for i in issues if i.pattern_name == "object_speaking"]
        assert len(errors) == 1

    def test_allows_person_speaking(self, linter):
        text = "她在说话。"
        issues = linter.check(text)
        errors = [i for i in issues if i.pattern_name == "object_speaking"]
        assert len(errors) == 0


class TestMindReading:
    def test_catches_mind_reading(self, linter):
        text = "她在想：如果那天早上我没去就好了。"
        issues = linter.check(text)
        errors = [i for i in issues if i.pattern_name == "mind_reading"]
        assert len(errors) == 1

    def test_allows_thinking_without_colon(self, linter):
        text = "她在想别的事情。"
        issues = linter.check(text)
        errors = [i for i in issues if i.pattern_name == "mind_reading"]
        assert len(errors) == 0


class TestGlobalRules:
    def test_she_doesnt_know_overuse(self, linter):
        text = "\n".join(["她不知道。"] * 5)
        issues = linter.check(text)
        global_issues = [i for i in issues if i.pattern_name == "she_doesnt_know_overuse"]
        assert len(global_issues) == 1
        assert global_issues[0].severity == Severity.WARNING

    def test_she_doesnt_know_within_limit(self, linter):
        text = "\n".join(["她不知道。"] * 3)
        issues = linter.check(text)
        global_issues = [i for i in issues if i.pattern_name == "she_doesnt_know_overuse"]
        assert len(global_issues) == 0


class TestCleanText:
    def test_clean_text_passes(self, linter):
        text = "弹簧在那个位置有一个弧度，布料在那里凹下去一块。声音闷一些，钝一些。"
        issues = linter.check(text)
        errors = [i for i in issues if i.severity == Severity.ERROR]
        assert len(errors) == 0


class TestFormatting:
    def test_format_report_clean(self, linter):
        report = linter.format_report([])
        assert "通过" in report

    def test_format_feedback_only_errors(self, linter):
        text = "她不知道。"  # INFO only, no errors
        issues = linter.check(text)
        feedback = linter.format_feedback_for_writer(issues)
        assert feedback == ""  # No errors -> no feedback for writer

    def test_format_feedback_has_errors(self, linter):
        text = "沙发记得他坐下的弧度。"
        issues = linter.check(text)
        feedback = linter.format_feedback_for_writer(issues)
        assert "必须修改" in feedback
