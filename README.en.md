# Study Arca · Information Asset Engineering

[中文](README.md) | English

Study Arca treats research information as **addressable, referenceable, verifiable, and versioned information assets**. Its toolchain projects those assets into reports, presentations, web documents, and other deliverables under explicit provenance and release constraints.

It manages more than documents. It manages the lifecycle of information from source intake and interpretation through design, freezing, composition, rendering, review, and publication.

## Core model

```text
Materials, evidence, work records
        ↓ normalize
Work state / Research IR
        ↓ alignment and freeze
Snapshot
        ↓ audience and narrative adaptation
ReportPlan / ContentMap / NarrativePlan
        ↓ compile
ReportDocument
        ↓ presentation backend
DeckPlan + RenderLayout
        ↓
DOCX / HTML / PPTX
        ↓ review and registration
Output / Review / Manifest
        ↓
Deliverable / Publish / Archive
```

This is an information-engineering analogue of source code, type checking, intermediate representations, build manifests, compiler backends, build artifacts, and release provenance.

| Software concept | Study Arca |
|---|---|
| Source | Materials, sources, work records, design records |
| Dependency | Cross-workspace references, external data, material hashes |
| Type system | Fact, inference, unknown, conflict, provenance, authority, confidence |
| Static analysis | `sa lint`, `synthesis validate`, `report validate`, reference and hash checks |
| IR | Research IR, Work Model, Work Snapshot, ReportDocument |
| Build manifest | ReportPlan, ContentMap, NarrativePlan |
| Code-generation IR | DeckPlan, RenderLayout |
| Backend | DOCX, HTML, PPTX renderers |
| Build provenance | Output registry, review, manifest |
| Release | `deliverables/`, `publish/` |
| Package | A `p-*` Workspace |
| Package graph | Program |
| Local compiler configuration | User and workspace dialects |

## Core objects

### Program

A Program is a thin Git superproject. It links Workspaces and pins their commits. It does not own source claims, work orders, reports, or outputs.

Programs are created at user-selected paths outside the product checkout. `sa` resolves a Program through `--program`, `SA_PROGRAM_ROOT`, or the nearest ancestor `program.json`.

### Workspace

A Workspace owns facts and outputs. There are two workspace identities:

- `research`: external investigation, evidence, analysis, and argument;
- `synthesis`: review, design, alignment, and audience-specific output for the researcher's own work.

### Information IR

Before output generation, information must be represented in a checkable form:

- what was observed;
- who supplied or published it;
- whether it is fact, inference, unknown, or disputed;
- which objects and relationships exist;
- which snapshot and version support the current claim.

Formats may change narrative, density, and presentation. They may not silently change the underlying information.

## What is `sa`?

`sa` is Study Arca's information language service, validator, dependency resolver, and build orchestrator.

It creates and validates Programs, Workspaces, and work orders; resolves references and versions; checks schemas, evidence chains, stage gates, and release boundaries; freezes snapshots; orchestrates ReportPlan and ReportDocument output; compiles DeckPlan/RenderLayout into native PPTX; and registers outputs and reviews.

Pylance is a useful partial analogy. More completely:

> `sa` = information language service + static analysis + dependency resolution + build orchestration.

## What is a Deck?

A Deck is one presentation compiler backend:

```text
Snapshot
→ ReportPlan / NarrativePlan
→ ReportDocument
→ DeckPlan + RenderLayout
→ PPTX
```

Presentation compilation intentionally compresses information. The compiler must preserve the meaning of released facts, evidence relationships, unknowns, and limitations. It must also record the audience, disclosure scope, omitted material, rendering environment, and visual review status.

## Main capabilities

- `research` and `synthesis` Workspace identities;
- material registration, hash checks, materialized cross-workspace references, and scoped dialects;
- review, design, alignment, advisory panels, research specialists, and knowledge/design baselines;
- source ledgers, claim/fact/conflict records, Research IR, and frozen snapshots;
- ReportPlan, ContentMap, NarrativePlan, and ReportDocument;
- DOCX, self-contained HTML, and native PPTX output;
- DeckPlan/RenderLayout, real PowerPoint rendering, per-slide measurement, and visual revision;
- output/review registration, immutable releases, and a stable release copy;
- explicit release packaging, development-history archives, and Git history maintenance;
- human documentation, agent skills, templates, and cases;
- Program submodules, recursive cloneable checks, and offline bundles.

## Quick start

```powershell
# Create a Program at a path chosen by the user
python scripts/sa.py program init <program-path> --id prog-main --title "My Research Program"

# Create Workspaces inside that Program
python scripts/sa.py new market-scan --title "Market scan" --type research --program <program-path>
python scripts/sa.py new project-review --title "Project review" --type synthesis --program <program-path>

python scripts/sa.py --help
python scripts/sa.py selftest
```

Program resolution order is:

1. `--program <path>`;
2. `SA_PROGRAM_ROOT`;
3. nearest ancestor `program.json`;
4. legacy product-local `work-root/` or `workspace/`, with a migration warning.

If a Program is specified, the new Workspace is created under `<program>/nodes/`, keeps its own Git repository, and is attached as a Program child.

## Representative workflows

### External research

```powershell
python scripts/sa.py cycle init <workspace>
python scripts/sa.py source <workspace> --title "..."
python scripts/sa.py research-ir build|validate|snapshot <workspace>
python scripts/sa.py lint <workspace>
```

### Review and design

```powershell
python scripts/sa.py input add <workspace> --file <material>
python scripts/sa.py synthesis init|status|apply|alignment|snapshot|build <workspace>
python scripts/sa.py synthesis validate <workspace>
```

### Report and presentation

```powershell
python scripts/sa.py report init <workspace> --id rpt-0001 --title "Report title"
python scripts/sa.py report build <workspace> --id rpt-0001 --format pptx
python scripts/sa.py deck validate <workspace> --plan <plan.json> --layout <layout.json>
python scripts/sa.py deck build <workspace> --plan <plan.json> --layout <layout.json> --output <deck.pptx>
python scripts/sa.py deck preview <workspace> --pptx <deck.pptx> --out-dir <preview-dir>
python scripts/sa.py output lint <workspace>
```

### Release and history

```powershell
python scripts/sa.py pack <workspace> --version v1.0
python scripts/sa.py report archive <workspace> --id rpt-0001 --before v1.0
python scripts/sa.py report archive <workspace> --id rpt-0001 --before v1.0 --apply
python scripts/sa.py report archive <workspace> --id rpt-0001 --before v1.0 --verify
```

## Boundaries

- A successful build does not prove that a claim is true. `sa` checks structure, references, completeness, and projection consistency; scientific truth still requires evidence, analysis, and human review.
- Audience adaptation may omit, summarize, or redact, but it must not alter released facts or remove limitations that change interpretation.
- Materials are dependencies, not conclusions.
- Formal output is built from frozen inputs, not mutable chat memory.
- Packaging, publication, and history cleanup are separate authorized actions.
- Program and Workspace data remain outside product Git history.

## Documentation

- [Human getting-started guide](docs/en/00-getting-started.md)
- [Documentation center](docs/en/README.md)

## License

Study Arca product code, specifications, templates, and skills are released under the [MIT License](LICENSE).
