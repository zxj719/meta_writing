# 设计决策归档

本目录索引项目历史上的设计文档与实施计划。

计划文件本身保留在 [`../superpowers/plans/`](../superpowers/plans/) —— 那是 superpowers 工具链写入的固定路径，移动会破坏工具约定。本文档提供索引与现状对照。

---

## 重要提醒

这些文档记录的是**当时的决策与理由**，不是当前状态的说明书。

- 判断系统**现在**怎么工作 → [`../architecture/`](../architecture/)
- 查某个字段/常量的**当前值** → [`../reference/`](../reference/)
- 理解某个设计**为什么**是现在这样 → 本目录

已实施的计划不会被回头更新。若计划描述与代码冲突，**以代码为准**。

---

## 计划索引

按时间倒序。

| 日期 | 计划 | 主题 | 当前状态 |
|------|------|------|---------|
| 2026-04-15 | [`editorial-scorecard-threshold`](../superpowers/plans/2026-04-15-editorial-scorecard-threshold.md) | 评分卡门槛体系：综合分 8.0 + 单维地板 7.0 + 停滞判断 | 已实施。现状见 [`../operations/editorial-scorecard-maintenance.md`](../operations/editorial-scorecard-maintenance.md) |
| 2026-04-11 | [`novel-quality-monitor`](../superpowers/plans/2026-04-11-novel-quality-monitor.md) | 章节质量监控与审稿留痕 | 已实施为 `editorial_reviews/NNN.{md,json}` |
| 2026-04-08 | [`workflow-modes-and-isolation`](../superpowers/plans/2026-04-08-workflow-modes-and-isolation.md) | manual / automatic 工作流模式互斥 | **已作废**：自动链路移除后 `workflow_mode` 一并删除 |
| 2026-04-08 | [`prompt-profile-decoupling`](../superpowers/plans/2026-04-08-prompt-profile-decoupling.md) | 把项目风格从 agent 提示词中解耦为独立档案 | 已实施为 [`prompt_profiles.py`](../../meta_writing/prompt_profiles.py) |
| 2026-04-08 | [`chapter-6-feedback-correction`](../superpowers/plans/2026-04-08-chapter-6-feedback-correction.md) | 针对第 6 章问题的定向修正 | 一次性修正，已完成 |
| 2026-04-06 | [`multi-novel-workspace`](../superpowers/plans/2026-04-06-multi-novel-workspace.md) | 多小说项目隔离与工作区管理 | 已实施为 [`workspace.py`](../../meta_writing/workspace.py)。用法见 [`../guides/multi-project-workspace.md`](../guides/multi-project-workspace.md) |
| 2026-04-06 | [`minimax-writer-and-novel-bootstrap`](../superpowers/plans/2026-04-06-minimax-writer-and-novel-bootstrap.md) | MiniMax 接入写手角色 + 新书引导流程 | **已作废**：供应商路由于 2026-09-09 整体移除，改为调用当前智能体。现状见 [`../architecture/agent-backend.md`](../architecture/agent-backend.md) |

### 已移除的计划

| 日期 | 计划 | 说明 |
|------|------|------|
| 2026-04-08 | `2026-04-08-auto-runner-self-correction.md` | 自动链路的跨章自我纠偏（`CarryoverCorrection`）。该文件连同 `auto_runner.py` 与 `tests/test_auto_runner.py` 已于 **2026-09-09** 随智能体后端迁移一并删除 |

---

## 演进脉络

七份计划连起来是一条清晰的能力累积线：

```
2026-04-06  可用           MiniMax 写手接入 + 新书引导
            可复用         多项目隔离，一本书不再污染另一本
                ↓
2026-04-08  可控           工作流模式互斥，自动循环不再覆写手工章节
            可定制         风格档案解耦，同一引擎服务不同审美
                ↓
2026-04-11  可观测         审稿留痕落盘，质量问题可回溯
                ↓
2026-04-15  可判定         五维评分卡 + 双重硬门槛 + 停滞退出
```

从「能写」到「能判断写得好不好」，再到「能解释为什么判定不好」。

2026-09-09 又加了一层**可移植**：全部 LLM 调用改为调用当前环境的智能体 CLI，不再绑定任何模型供应商，同时移除了自动链路与 `workflow_mode`。设计见 [`../superpowers/specs/2026-09-09-agent-backend-migration-design.md`](../superpowers/specs/2026-09-09-agent-backend-migration-design.md)。

---

## 其他历史材料

仓库根目录还有两份未纳入本索引的历史文件：

| 文件 | 内容 |
|------|------|
| `TODOS.md` | 早期待办与已完成项记录 |
| `skills_novel-writing-expert-v2.md` | 写作方法论材料 |
| `会话记录_2026-03-26_28.md` | 早期开发会话记录 |

它们是过程材料而非项目文档，暂保留在根目录。
