# 16 · Synthesis and Output

[中文](../16-复盘对齐与适配输出.md) | English

## Two processes

Synthesis supports:

- **review**: turn raw material into complete, structured current state;
- **design**: turn constraints and alternatives into an accepted design baseline.

They may run separately or in one mixed loop.

## Work loop

```text
User narration and materials
→ structured work state
→ gaps and focused questions
→ user correction
→ alignment
→ frozen snapshot
→ audience-specific output
```

The agent should first reflect what it heard, then ask a small number of high-impact questions. “Unknown” and “skip” are valid answers.

## Stages

- G1: review complete enough for user inspection.
- G2: terms, scope, causal explanation, and design choices aligned.
- G3: snapshot is immutable and independently readable.
- G4: audience, disclosure scope, format, and release constraints are explicit.

## Records

- `work-model/model.json`: editable current state;
- `synthesis/ledger.json`: append-only cognitive events and design decisions;
- `synthesis/alignments/`: human-readable alignment records;
- `synthesis/snapshots/`: frozen inputs;
- `outputs/registry.json`: output and review provenance.

## Output

Formal multi-audience output uses `sa report`; presentation uses DeckPlan/RenderLayout and visually inspected PPTX. Packaging and development-history cleanup are separate actions.
