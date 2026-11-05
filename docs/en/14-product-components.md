# 14 · Product Components

[中文](../14-产品组件与资产.md) | English

| Component | Responsibility |
|---|---|
| `docs/` | Human documentation and normative authority |
| `.agents/skills/` | Agent task routing and execution protocol |
| `templates/` | Reusable project, report, PPT, and research structures |
| `src/`, `scripts/` | Public implementation and CLI |
| User Program | Member Workspaces and commit pins |
| `work-root/`, `workspace/` | Legacy compatibility only; not product defaults |
| `RELEASE.json`, `VERSION` | Product release identity and integrity |

## Main implementation modules

- `project.py`, `workspace.py`: scaffolding, identity, work orders, materials, references, dialects;
- `program.py`: Program graph, submodules, clone and bundle;
- `evidence.py`, `cycle.py`, `research_ir.py`: research state and evidence;
- `synthesis.py`: review, design, alignment, baselines, snapshots;
- `reporting.py`, `report_outputs.py`, `output_registry.py`: reports and output review;
- `deck.py`, `preview.py`: native PPTX and rendering;
- `report_archive.py`, `pack.py`: development-history archive and release packaging.

## Boundary

Skills do not become evidence. Templates contain placeholders only. Current research data stays in the owning Workspace. Program and Workspace content never enter product Git history.
