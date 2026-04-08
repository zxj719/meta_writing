# Multi-Project Workspace

`meta_writing` now supports a shared workspace with multiple novel projects under `novels/`.

## Layout

```text
meta_writing/
  novels/
    current-book/
      story_data/
      chapters/
      learned_rules.md
      auto_runner_log.md
      editorial_report.md
    next-book/
      ...
  .meta-writing/
    workspace.json
```

## Migrate the current novel out of the repo root

From the `meta_writing` repo root:

```powershell
meta-writing project create current-book --from-project-dir . --move-source --activate
```

This copies the active story files into `novels/current-book/`, removes the moved files from the repo root, and marks `current-book` as the active project.

If you want to keep the root files for comparison, use `--copy-source` instead.

## Create the next novel quickly

```powershell
meta-writing project create next-book --activate
meta-writing init --project next-book
```

After that, all normal commands can target the new project:

```powershell
meta-writing status --project next-book
meta-writing generate --project next-book
python auto_runner.py --project next-book --workspace-dir .
python scripts/editorial_pass.py --project next-book --workspace-dir .
```

## Active project behavior

If you run commands from the workspace root and an active project is set, `meta_writing` now resolves to the active project by default.

If you still need to target the old repo root as a legacy project, use:

```powershell
meta-writing --project-dir .
python auto_runner.py --project-dir .
python scripts/editorial_pass.py --project-dir .
```
