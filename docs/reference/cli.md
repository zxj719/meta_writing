# CLI 参考

> 代码位置：[`meta_writing/cli.py`](../../meta_writing/cli.py)

两种调用方式等价：

```powershell
meta-writing <command>                      # 安装后（pyproject 的 console script）
python -m meta_writing.cli <command>        # 免安装
```

---

## 1. 全局选项

所有选项作用于 `cli` 组，必须写在子命令**之前**。

| 选项 | 默认 | 说明 |
|------|------|------|
| `--workspace-dir PATH` | `.` | 工作区根目录（内含 `novels/` 项目库） |
| `--project NAME` | 无 | 工作区内的项目名 |
| `--project-dir PATH` | 无 | 直接指定项目目录，绕过工作区解析 |

```powershell
meta-writing --workspace-dir . --project rescue-male-lead status
```

### 项目解析顺序

除 `project` 子命令组外，每次调用都会解析出一个项目目录，顺序为（[`WorkspaceManager.resolve_project_dir`](../../meta_writing/workspace.py)）：

1. `--project-dir` 显式指定 → 直接用
2. `--project` 指定 → `novels/<name>/`，不存在则报错
3. 当前工作目录 == 工作区根 **且** 有激活项目 → 用激活项目
4. 从当前目录向上找含 `story_data/` 或 `chapters/` 的祖先目录
5. 有激活项目 → 用激活项目
6. 工作区根仍有遗留小说文件 → **报错**，要求先迁移或显式指定
7. 兜底：用当前目录

第 6 条是防止误伤：工作区根同时存在 `novels/` 和遗留的根级小说文件时，系统拒绝猜测，必须显式选择。

---

## 2. `project` — 项目管理

这组子命令**不解析项目目录**，可在没有任何项目时运行。

### `project create NAME`

创建项目脚手架：建 `story_data/` 与 `chapters/`、写 `.meta-writing-project.json`、生成 `creator_guidance.md` 模板。

| 选项 | 默认 | 说明 |
|------|------|------|
| `--mode manual\|automatic` | `manual` | 工作流模式 |
| `--activate / --no-activate` | `--activate` | 是否设为当前激活项目 |
| `--from-project-dir PATH` | 无 | 从既有项目目录导入内容 |
| `--move-source / --copy-source` | `--copy-source` | 导入后是否删除源文件 |

导入范围固定为 `PROJECT_COPY_ITEMS`：`story_data`、`chapters`、`learned_rules.md`、`auto_runner_log.md`、`editorial_report.md`、`creator_guidance.md`。

项目已存在时抛 `FileExistsError`。

```powershell
meta-writing --workspace-dir . project create my-new-novel --mode manual --activate
```

### `project list`

列出全部项目，格式 `<名称> [<模式>]`，激活项目附 ` (active)`。

### `project use NAME`

设为激活项目，写入 `.meta-writing/workspace.json`。项目不存在则报错。

### `project current`

打印当前激活项目名。

### `project mode MODE`

修改工作流模式。`MODE` 取 `manual` 或 `automatic`。

| 选项 | 默认 |
|------|------|
| `--name NAME` | 当前激活项目 |

无激活项目且未传 `--name` 时报错。

### `project migrate-root NAME`

把工作区根的遗留小说文件迁进 `novels/<NAME>/`。

| 选项 | 默认 |
|------|------|
| `--move-source / --copy-source` | `--move-source` |
| `--mode manual\|automatic` | `manual` |
| `--activate / --no-activate` | `--no-activate` |

注意此命令的 `--move-source` 与 `--activate` 默认值都与 `project create` 相反。

---

## 3. `init` — 初始化故事核心

交互式创建 `story_data/story_core.yaml`。

依次提问：

| 提问 | 默认 | 落到字段 |
|------|------|----------|
| 一句话核心 (Hook) | 无（必填） | `hook` |
| 体裁编号（10 选 1） | `1` | `genre` |
| 核心爽点类型 | 空 | `target_satisfaction_type` |
| 计划总章节数 | `100` | `total_planned_chapters` |
| Writer provider | `minimax` | `writer_provider` |
| Target chapter chars | `2000` | `chapter_target_chars` |
| Minimum chars before expansion | `max(800, 目标×0.8)` | `chapter_min_chars` |
| 伏笔最大寿命 | 按体裁：玄幻 30 / 言情 15 / 悬疑 20 / 其他 20 | `foreshadowing_max_age_chapters` |
| 五层世界架构（可回车跳过） | 空 | `world_layers` |

最后询问是否添加第一个角色。

> 已存在 `story_core.yaml` 时，本命令会**直接覆盖**，无确认提示。

---

## 4. `generate` — 生成下一章

跑完整手动流水线。要求项目处于 `manual` 模式，否则抛 `ClickException`。

| 选项 | 说明 |
|------|------|
| `--guidance TEXT` | 附加创作指导，与 `creator_guidance.md` 的内容合并后传给全部 agent |

```powershell
meta-writing --project rescue-male-lead generate --guidance "继续下一章，写完后更新角色状态、伏笔、时间线和节奏。"
```

### 交互流程

1. **分支选择** — 每条分支以表格展示大纲、涉及角色、影响、爽点级别、钩子类型、风险等级，输入序号
2. **章节审查** — 展示正文（超 2000 字截断）与连续性问题，选 `approve` / `reject` / `edit`
   - `edit` 会追问"备注/修改内容"，**输入的文本将整体替换正文**
   - `reject` 终止流程，不落盘
3. **状态变更确认** — 表格展示角色/字段/旧值/新值，确认后写回 Story Bible

完成后打印章节字数、token 用量与预估成本。

> 成本估算按 MiniMax 定价计算。写手切到 DeepSeek 时，其用量不计入 `orch.llm.usage`，报告会低估。

---

## 5. `status` — 查看 Story Bible 状态

只读，不调用 LLM。输出：

- 故事核心：Hook、体裁、当前章节、计划章节
- 角色表：名称、动机类型、成长阶段、位置
- 活跃伏笔表：ID、描述（截 40 字）、植入章节、年龄
- 计数：时间线事件数、世界规则数、章节摘要数

`story_core.yaml` 缺失或非法时打印错误并提示运行 `init`，不抛异常。

---

## 6. `add-character` — 添加角色

交互式创建一张角色卡，写入 `story_data/characters/<name>.yaml`。

提问：角色名、外貌描述、性格特征（逗号分隔）、核心三角（欲望/能力/阻碍）、动机类型、是否 POV。

其余字段（`knowledge_state`、`relationships`、`current_goals`、`backstory` 等）需手工编辑 YAML 补充。

---

## 7. 非 CLI 入口

以下两个脚本不属于 `meta-writing` 命令组，直接用 `python` 运行，但共享同一套项目解析参数（`--workspace-dir` / `--project` / `--project-dir`）。

### `auto_runner.py` — 自动生成循环

要求项目处于 `automatic` 模式。

```powershell
python auto_runner.py --project <name> --from 1 --to 10
python auto_runner.py --project <name> --to 10 --dry-run
python auto_runner.py --project <name> --to 10 --push
```

| 参数 | 默认 | 说明 |
|------|------|------|
| `--from N` | `current_chapter + 1` | 起始章 |
| `--to N` | `20` | 结束章（含） |
| `--writer-provider` | 项目配置 | 覆盖写手供应商 |
| `--dry-run` | 关 | 只规划选枝，不写不提交 |
| `--push` | 关 | 每章后 git push |

详见 [`../architecture/pipelines.md`](../architecture/pipelines.md)。

> 该文件在工作区中存在未提交的删除。

### `scripts/editorial_pass.py` — 独立审稿

对已有章节单独跑一遍审稿，不生成新内容。

```powershell
python scripts/editorial_pass.py --project <name> --workspace-dir .
```
