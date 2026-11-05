# 00 · Getting Started

[中文](../00-使用指南.md) | English

This guide is the first entry point for Study Arca users. It explains the system shape, workspace types, common commands, and where detailed authority lives.

## System model

```text
Program
  └─ Workspace
       ├─ brief/
       ├─ work-orders/
       ├─ references/
       ├─ synthesis/ or research/
       ├─ report/
       ├─ outputs/
       ├─ deliverables/
       ├─ archive/
       └─ publish/
```

A Program is a thin graph of member Workspaces. A Workspace owns facts, work orders, evidence, reports, reviews, and releases.

## Workspace identities

- `research`: external investigation, source collection, analysis, and argument.
- `synthesis`: review, design, alignment, freezing, and audience-specific output for the researcher's own work.

The identity is stored in `project.json`; it is never inferred from a directory name.

## First use

```powershell
# Create a Program outside the product checkout
python scripts/sa.py program init <program-path> --id prog-main --title "My Research Program"

# Create a research Workspace
python scripts/sa.py new market-scan --title "Market scan" --type research --program <program-path>

# Create a synthesis Workspace
python scripts/sa.py new project-review --title "Project review" --type synthesis --program <program-path>
```

Program resolution order:

1. `--program`;
2. `SA_PROGRAM_ROOT`;
3. nearest ancestor `program.json`;
4. legacy product-local `work-root/` or `workspace/`, with a migration warning.

`--root` is a low-level escape hatch: it selects only a workspace container and does not attach the new Workspace to a Program. Normal use should establish a Program first.

The product repository does not contain a default data root.

## Reports and presentations

```powershell
python scripts/sa.py report init <workspace> --id rpt-0001 --title "Report title"
python scripts/sa.py report build <workspace> --id rpt-0001 --format pptx
python scripts/sa.py deck validate <workspace> --plan <plan.json> --layout <layout.json>
python scripts/sa.py deck build <workspace> --plan <plan.json> --layout <layout.json> --output <deck.pptx>
python scripts/sa.py deck preview <workspace> --pptx <deck.pptx> --out-dir <preview-dir>
python scripts/sa.py output lint <workspace>
```

## Release lifecycle

| Location/action | Purpose |
|---|---|
| `publish/vX.Y/` | Immutable release |
| `publish/release/` | Latest stable release copy |
| `sa pack` | Explicit external delivery archive |
| `sa report archive` | Retire superseded development artifacts |

Packaging, publication, and Git history cleanup are separate authorized actions.

## Recommended reading

- Workspace model: [02](02-project-layout.md), [15](15-workspaces-and-programs.md)
- Research: [09](09-research-loop.md), [03](03-evidence-and-traceability.md)
- Review/design: [16](16-synthesis-and-output.md), [17](17-collaboration-roles.md)
- Reports/PPT: [18](18-report-orchestration.md), [11](11-ppt-design.md), [07](07-delivery-and-ppt.md)
