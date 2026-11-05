# 02 · Project Layout

[中文](../02-项目布局.md) | English

## Product and data separation

`study-arca` is the product checkout. It contains code, specifications, templates, and skills. User Programs and Workspaces live outside the product tree.

`--root` remains available for compatibility and explicit container-only workflows. It does not create Program ownership.

```text
Product checkout
  └── code / docs / templates / skills

User-selected Program
  ├── program.json
  ├── .gitmodules
  └── nodes/
      └── p-YYYYMMDD-slug/
```

## Workspace layout

```text
p-YYYYMMDD-slug/
├── project.json
├── brief/
├── work-orders/
├── references/
├── synthesis/          # synthesis Workspaces
├── research/           # research Workspaces
├── report/
├── outputs/
├── deliverables/
├── publish/
└── archive/
```

## Responsibilities

| Path | Responsibility |
|---|---|
| `brief/` | User-provided requirements, statements, and materials |
| `work-orders/` | Workspace-owned tasks |
| `references/` | Immutable copies of facts referenced from other Workspaces |
| `synthesis/` | Review/design events, alignments, snapshots |
| `research/` | Research loop records and frozen artifacts |
| `report/` | Regenerable plans, layouts, outputs, previews |
| `outputs/` | Output and review audit registry |
| `deliverables/` | Frozen internal delivery snapshots |
| `publish/` | Immutable external releases |
| `archive/` | Retired development history |

## Schedules and references

Large external datasets may be referenced rather than copied when they are stable and frozen. Direct material used to support a Workspace claim must have a verifiable identity, hash, or immutable copy.

## Lifecycle

Workspace status: `active`, `suspended`, or `archived`. Delivery is recorded separately from research status.
