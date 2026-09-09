# 测试与发布卫生

---

## 1. 测试套件

框架：pytest + pytest-asyncio（`asyncio_mode = "auto"`，异步测试无需装饰器）+ pytest-mock。

```powershell
python -m pytest -q                          # 全部
python -m pytest tests/test_style_linter.py -q   # 单文件
python -m pytest -m integration              # 真实 LLM 调用（会消耗额度）
```

**全部单元测试中的 LLM 调用都是 mock 的**，不消耗 API 额度、不需要配置密钥。只有 `@pytest.mark.integration` 标记的测试会真实调用。

### 覆盖范围

| 测试文件 | 覆盖 |
|---------|------|
| `test_story_bible.py` | schema 校验、YAML 往返、压缩三级降级 |
| `test_workspace.py` | 多项目隔离、工作流模式、项目解析顺序 |
| `test_orchestrator.py` | 流水线状态机、审稿循环、落盘 |
| `test_planner.py` | JSON 多级修复、兜底分支 |
| `test_writer.py` | 写作/扩写/修订路由、字数触发 |
| `test_continuity.py` / `test_style_agent.py` / `test_theme.py` | 响应解析与降级 |
| `test_editorial_scorecard.py` | 加权聚合、门槛、停滞判断 |
| `test_style_linter.py` | 正则规则的正例与反例 |
| `test_prompt_profiles.py` | 档案识别与提示词拼接 |
| `test_llm.py` | 重试、退避、供应商归一化 |
| `test_vector_store.py` | 分块策略 |

### 改动后必须补测的位置

| 改了什么 | 至少要加 |
|---------|---------|
| style linter 规则 | 正例 **+ 反例**（确保不误伤正常文本） |
| 评分阈值/权重 | `test_editorial_scorecard.py` 的边界用例 |
| Story Bible schema | YAML 往返 + 缺字段的降级行为 |
| 审稿 agent | 解析失败时的降级返回值 |
| 编排逻辑 | **两条链路都要改、都要测**（见下） |

> `orchestrator.py` 与 `auto_runner.py` 的审稿逻辑是各自实现的。只改一边、只测一边，会产生「手动更严、自动更松」的静默偏差。

---

## 2. 手工验证

单元测试覆盖不到的两件事，改动核心链路后应手工确认。

### Story Bible 能加载

```powershell
@'
from pathlib import Path
from meta_writing.story_bible.loader import StoryBibleLoader
bible = StoryBibleLoader(Path("novels/<name>/story_data")).load()
print("current_chapter  =", bible.core.current_chapter)
print("characters       =", len(bible.characters))
print("chapter_summaries=", len(bible.chapter_summaries))
'@ | python -X utf8 -
```

### 压缩级别符合预期

状态膨胀后，确认压缩没有意外降到 `minimal`：

```powershell
@'
from pathlib import Path
from meta_writing.story_bible.loader import StoryBibleLoader
from meta_writing.story_bible.compressor import StoryBibleCompressor
bible = StoryBibleLoader(Path("novels/<name>/story_data")).load()
ctx = StoryBibleCompressor().compress(bible, bible.core.current_chapter + 1)
print("level =", ctx.compression_level, "| tokens =", ctx.estimated_tokens)
'@ | python -X utf8 -
```

降到 `minimal` 意味着世界规则、时间线、爽点排期都已被丢弃，只剩 POV 角色和临期伏笔——生成质量会明显下降。此时应考虑精简角色卡的冗余描述，或调大 `token_budget`。

---

## 3. 提交前检查

```powershell
git status --short
python -m pytest -q
git diff --check                 # 行尾空白、冲突标记
```

### 密钥扫描

```powershell
rg -n "sk-|API_KEY\s*=|AUTH_TOKEN\s*=|BEGIN .*PRIVATE KEY" .
```

`.gitignore` 已排除 `.env` / `.env.local`，但手工新建的配置文件不在其列。**每次提交前扫一遍**。

`.gitignore` 已覆盖的运行时产物：

```
**/auto_runner_log.md
**/editorial_report.md
_planner_result*.json
.meta-writing/
.chromadb/
```

注意 `editorial_reviews/` **不在忽略列表中**——逐章审稿记录是有意纳入版本控制的，它是质量趋势的唯一历史来源。

---

## 4. 提交约定

**章节与其状态更新必须在同一个提交里。** 只有正文没有 Story Bible 更新的提交视为不完整——后续 `git bisect` 定位质量问题时，这类提交会让状态与正文对不上。

```powershell
git add novels/<name>/chapters/NNN.md novels/<name>/story_data novels/<name>/editorial_reviews
git commit -m "chapter NNN: <一句话内容>"
git push origin master
```

前缀约定：

| 前缀 | 用于 |
|------|------|
| `feat:` | 新功能 |
| `fix:` | 缺陷修复 |
| `docs:` | 文档 |
| `refactor:` | 重构 |
| `chapter NNN:` | 章节产出 |

---

## 5. 自动提交的静默失败

两条链路都会在落盘后尝试 `git add` + `git commit`：

```python
try:
    subprocess.run(["git", "add", "story_data/", "chapters/"], cwd=..., check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", f"chapter {n:03d}: ..."], cwd=..., check=True, capture_output=True)
except subprocess.CalledProcessError:
    pass
```

`except ... : pass` 意味着**所有 git 失败都被吞掉**，且 `capture_output=True` 让错误信息也不可见。常见失败原因：

- 项目目录不在 git 仓库内
- 未配置 `user.name` / `user.email`
- 没有变更可提交
- 存在 pre-commit hook 且失败

生成后请自行确认：

```powershell
git log -1 --stat
```

---

## 6. 相关文档

- 评分体系的调参与维护：[`editorial-scorecard-maintenance.md`](editorial-scorecard-maintenance.md)
- 日常写作循环：[`../guides/manual-chapter-workflow.md`](../guides/manual-chapter-workflow.md)
- 常量与配置项位置：[`../reference/configuration.md`](../reference/configuration.md)
