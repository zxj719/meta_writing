"""Tests for Vector Store (chunking logic only — no real embeddings)."""

from __future__ import annotations

import pytest

from meta_writing.vector_store.store import chunk_chapter


SAMPLE_CHAPTER = """\
夜色笼罩着临海市，路灯在薄雾中散发出昏黄的光晕。林越站在教学楼的走廊上，手心微微出汗。

他的左眼再次隐隐作痛——就像那天放学路上一样。透过指缝，他看到了不该看到的东西。

***

地下室的门开着，一股阴冷的气息从门缝中涌出。林越犹豫了一下，还是走了进去。

走廊很长，墙壁上布满了不知名的符文，在微弱的光芒中若隐若现。

***

"你不该来这里。"

一个低沉的声音从黑暗中传来。林越猛地停下脚步，异能自动激活，空间感知扩展到了极限。

"谁？"他的声音在空旷的地下室中回荡。
"""


class TestChunking:
    def test_basic_chunking(self):
        # Make each scene long enough to exceed CHUNK_MIN_SIZE individually
        long_chapter = (
            "夜色笼罩着临海市。" * 40 + "\n\n***\n\n" +
            "地下室的门开着。" * 40 + "\n\n***\n\n" +
            "一个低沉的声音从黑暗中传来。" * 40
        )
        chunks = chunk_chapter(long_chapter)
        assert len(chunks) >= 2  # Should split on *** separators

    def test_empty_text(self):
        assert chunk_chapter("") == []
        assert chunk_chapter("   ") == []

    def test_short_text_single_chunk(self):
        short = "这是一个很短的段落。"
        chunks = chunk_chapter(short)
        assert len(chunks) == 1

    def test_scene_separators_respected(self):
        text = "场景一内容" * 50 + "\n\n***\n\n" + "场景二内容" * 50
        chunks = chunk_chapter(text)
        assert len(chunks) >= 2

    def test_long_scene_split_on_paragraphs(self):
        # Create a scene longer than CHUNK_MAX_SIZE
        long_scene = "\n\n".join(["这是第{}段的内容，描写了很长的场景。" * 10] * 20)
        chunks = chunk_chapter(long_scene)
        assert len(chunks) >= 2
        for chunk in chunks:
            assert len(chunk) > 0

    def test_preserves_content(self):
        chunks = chunk_chapter(SAMPLE_CHAPTER)
        # All content should be present across chunks
        combined = " ".join(chunks)
        assert "林越" in combined
        assert "地下室" in combined
        assert "空间感知" in combined

    def test_dash_separator(self):
        text = "场景一" * 100 + "\n\n---\n\n" + "场景二" * 100
        chunks = chunk_chapter(text)
        assert len(chunks) >= 2
