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

    def test_catches_contrast_scaffold_overuse(self, linter):
        text = "\n".join(
            [
                "她想说点轻松的，但嗓子还是发紧。",
                "他已经站稳了，但指节还是绷着。",
                "走廊里没什么人，但空气还是压得人难受。",
                "她嘴上说得很快，但心里其实还悬着。",
                "他看起来很冷静，但呼吸还是乱了一拍。",
                "雨已经停了，但楼外的地面还泛着冷光。",
                "她本来想笑一下，但最后只抿了抿唇。",
                "他没有回头，但脚步明显慢了半拍。",
                "事情已经结束了，但谁都没有真正松下来。",
            ]
        )
        issues = linter.check(text)
        global_issues = [i for i in issues if i.pattern_name == "contrast_scaffold_overuse"]
        assert len(global_issues) == 1
        assert global_issues[0].severity == Severity.ERROR

    def test_catches_short_sentence_tic_overuse(self, linter):
        text = "\n".join(
            [
                "很好。",
                "很轻。",
                "很慢。",
                "很低。",
                "很稳。",
            ]
        )
        issues = linter.check(text)
        global_issues = [i for i in issues if i.pattern_name == "short_sentence_tic_overuse"]
        assert len(global_issues) == 1
        assert global_issues[0].severity == Severity.WARNING

    def test_catches_negation_parallelism_overuse(self, linter):
        text = "\n".join(
            [
                "这不是普通的紧张，是整根神经都绷着。",
                "这不是她多心，是走廊里的风都不对。",
                "不是他不想说，是他根本开不了口。",
                "这不是旧账翻出来，是有人把刀重新递到了眼前。",
                "不是顾夜舟反应太大，是这疯子说话太恶心。",
            ]
        )
        issues = linter.check(text)
        global_issues = [i for i in issues if i.pattern_name == "negation_parallelism_overuse"]
        assert len(global_issues) == 1
        assert global_issues[0].severity == Severity.WARNING

    def test_catches_this_too_template_once(self, linter):
        text = "这件事也太离谱了。"
        issues = linter.check(text)
        errors = [i for i in issues if i.pattern_name == "this_too_template"]
        assert len(errors) == 1
        assert errors[0].severity == Severity.ERROR

    def test_catches_negation_definition_once(self, linter):
        text = "不是，是她真的听见了门外的脚步声。"
        issues = linter.check(text)
        errors = [i for i in issues if i.pattern_name == "negation_definition_template"]
        assert len(errors) == 1
        assert errors[0].severity == Severity.ERROR

    def test_catches_three_tiny_paragraphs_in_a_row(self, linter):
        text = "\n\n".join(["停。", "别动。", "听。", "楼下的灯忽然灭了。"])
        issues = linter.check(text)
        errors = [i for i in issues if i.pattern_name == "tiny_paragraph_triplet"]
        assert len(errors) == 1
        assert errors[0].severity == Severity.ERROR

    def test_catches_flat_expression_templates(self, linter):
        text = "\n".join(["他的脸色沉下去。", "她的眼神冷下去。"])
        issues = linter.check(text)
        errors = [i for i in issues if i.pattern_name == "flat_expression_template"]
        assert len(errors) == 2
        assert all(issue.severity == Severity.ERROR for issue in errors)

    def test_catches_na_intensifier_but_scaffold(self, linter):
        text = "那一眼很轻，但顾夜舟还是看懂了。"
        issues = linter.check(text)
        errors = [i for i in issues if i.pattern_name == "na_intensifier_but_scaffold"]
        assert len(errors) == 1
        assert errors[0].severity == Severity.ERROR

    def test_catches_na_negation_but_scaffold(self, linter):
        text = "那不是普通提醒，但沈清辞没有立刻追问。"
        issues = linter.check(text)
        errors = [i for i in issues if i.pattern_name == "na_negation_but_scaffold"]
        assert len(errors) == 1
        assert errors[0].severity == Severity.ERROR

    def test_catches_opening_yi_jiu_scaffold_after_heading(self, linter):
        text = "# 第1章 测试\n\n成人礼一结束，礼堂门口就乱成一锅粥。\n\n后面是正文。"
        issues = linter.check(text)
        errors = [i for i in issues if i.pattern_name == "opening_yi_jiu_scaffold"]
        assert len(errors) == 1
        assert errors[0].severity == Severity.ERROR

    def test_allows_yi_jiu_scaffold_after_opening(self, linter):
        text = "# 第1章 测试\n\n礼堂门口还在吵。\n\n成人礼一结束，大家就往外跑。"
        issues = linter.check(text)
        errors = [i for i in issues if i.pattern_name == "opening_yi_jiu_scaffold"]
        assert len(errors) == 0


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
