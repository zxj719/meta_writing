# 文档索引

`meta_writing` 的全部项目文档。按用途分四层，另有一个历史设计归档。

---

## 我想…

| 目标 | 去这里 |
|------|--------|
| 第一次把它跑起来 | [`guides/getting-started.md`](guides/getting-started.md) |
| 理解系统怎么设计的 | [`architecture/overview.md`](architecture/overview.md) |
| 开一本新书 | [`guides/new-novel-quickstart.md`](guides/new-novel-quickstart.md) |
| 长期写作的日常循环 | [`guides/manual-chapter-workflow.md`](guides/manual-chapter-workflow.md) |
| 查某个 CLI 命令 | [`reference/cli.md`](reference/cli.md) |
| 查某个 YAML 字段 | [`reference/story-bible-schema.md`](reference/story-bible-schema.md) |
| 改某个阈值/环境变量 | [`reference/configuration.md`](reference/configuration.md) |
| 质量不满意，想调审稿标准 | [`operations/editorial-scorecard-maintenance.md`](operations/editorial-scorecard-maintenance.md) |
| 加一条文风规则 | [`reference/style-rules.md`](reference/style-rules.md) |
| 加一位审稿 agent | [`architecture/agents.md`](architecture/agents.md) |

---

## architecture/ — 设计

系统怎么组织、为什么这么组织。改动核心链路前先读。

| 文档 | 内容 |
|------|------|
| [`overview.md`](architecture/overview.md) | **总体设计**：四层架构、一章的生命周期、六条核心设计原则、稳健性策略 |
| [`story-bible.md`](architecture/story-bible.md) | 状态层：数据模型、装载持久化、三级上下文压缩、状态更新路径 |
| [`agents.md`](architecture/agents.md) | 智能体层：五个常驻 agent 的职责与契约、JSON 稳健性、如何扩展 |
| [`pipelines.md`](architecture/pipelines.md) | 编排层：手动与自动两条链路的完整对比、工作流模式互斥、已知缺口 |
| [`model-routing.md`](architecture/model-routing.md) | 三个 LLM client、按角色的模型分派、三级供应商回退、配置陷阱 |

---

## guides/ — 操作指南

按任务组织的操作步骤。

| 文档 | 内容 |
|------|------|
| [`getting-started.md`](guides/getting-started.md) | 从安装到生成第一章 |
| [`new-novel-quickstart.md`](guides/new-novel-quickstart.md) | 开新书的完整清单 |
| [`manual-chapter-workflow.md`](guides/manual-chapter-workflow.md) | 手动章节循环、落盘后的人工补齐、周期性复盘 |
| [`multi-project-workspace.md`](guides/multi-project-workspace.md) | 多项目工作区、迁移遗留项目、项目切换 |

---

## reference/ — 参考

查阅型文档，不讲原理只列事实。

| 文档 | 内容 |
|------|------|
| [`cli.md`](reference/cli.md) | 全部命令、选项、默认值、项目解析顺序 |
| [`story-bible-schema.md`](reference/story-bible-schema.md) | 全部 YAML 字段、类型、默认值、枚举取值 |
| [`configuration.md`](reference/configuration.md) | 环境变量、项目配置、代码常量、已知配置陷阱 |
| [`style-rules.md`](reference/style-rules.md) | Linter 全部规则、反例库、提示词禁止清单 |

---

## operations/ — 运维与调参

系统跑起来之后的持续维护。

| 文档 | 内容 |
|------|------|
| [`editorial-scorecard-maintenance.md`](operations/editorial-scorecard-maintenance.md) | **评分体系维护手册**：五维权重、硬门槛、聚合逻辑、常见维护场景、调参原则 |
| [`testing-and-verification.md`](operations/testing-and-verification.md) | 测试套件、手工验证、提交前检查、密钥扫描 |

---

## decisions/ — 设计决策归档

历史设计文档与实施计划，见 [`decisions/README.md`](decisions/README.md)。

这些文档记录的是**当时的决策与理由**，不保证与当前代码一致。判断现状请以 `architecture/` 与 `reference/` 为准。

---

## 文档维护约定

1. **`architecture/` 讲为什么，`reference/` 讲是什么，`guides/` 讲怎么做。** 同一事实不要在三处重复展开，用链接指过去。
2. **改代码时同步改文档。** 尤其是 `reference/configuration.md` 里的常量表——它是唯一一处集中记录硬编码阈值的地方。
3. **文档里的断言必须能在代码里找到依据。** 本文档集中的每处「未被调用」「静默失败」「两处不一致」都经过实际验证；新增此类断言前请同样验证。
4. **不要新建根级 `.md`。** 新文档进 `docs/` 的对应子目录，并在本索引登记。
