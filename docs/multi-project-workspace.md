# Multi-Project Workspace

`meta_writing` now supports a shared workspace with multiple novel projects under `novels/`.

## Workflow modes

Each project now has an explicit workflow mode in `.meta-writing-project.json`:

- `manual`: use `meta-writing generate` and keep humans in branch selection / review / revision.
- `automatic`: use `python auto_runner.py ...` and let the full auto pipeline run.

The tools now enforce this split. A `manual` project will reject `auto_runner.py`, and an `automatic` project will reject `meta-writing generate`.

## Layout

```text
meta_writing/
  novels/
    current-book/
      story_data/
      chapters/
      .meta-writing-project.json
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
meta-writing project migrate-root current-book --activate
```

This copies the root-level story files into `novels/current-book/`, removes the moved files from the repo root, and marks `current-book` as the active project.

If you want to keep the root files for comparison, use `--copy-source` instead.

## Create the next novel quickly

```powershell
meta-writing project create next-book --mode manual --activate
meta-writing init --project next-book
```

After that, all normal commands can target the new project:

```powershell
meta-writing status --project next-book
meta-writing generate --project next-book
python scripts/editorial_pass.py --project next-book --workspace-dir .
```

If you want a fully automatic novel project instead:

```powershell
meta-writing project create auto-book --mode automatic --activate
python auto_runner.py --project auto-book --workspace-dir .
```

## Active project behavior

If you run commands from the workspace root and an active project is set, `meta_writing` now resolves to the active project by default.

If the workspace root still contains a legacy novel, the tools now refuse to select it implicitly. Migrate it first with `project migrate-root`, or target it explicitly:

```powershell
meta-writing --project-dir .
python auto_runner.py --project-dir .
python scripts/editorial_pass.py --project-dir .
```
