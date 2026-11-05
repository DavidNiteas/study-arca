# 18 · Report Orchestration

[中文](../18-报告编排与输出.md) | English

## Position

A report is an independent narrative product derived from frozen content. Audience, purpose, disclosure scope, and format shape selection and order, not facts.

## Pipeline

```text
Frozen sources
→ ReportBrief
→ ContentMap
→ NarrativePlan
→ ReportDocument
→ DOCX / HTML / PPTX
→ preview and review
→ output registry
```

## Components

- **ContentMap**: what is used, omitted, compressed, deferred, or redacted and why.
- **NarrativePlan**: perspective, claims, structure, release level, detail level.
- **ReportDocument**: format-neutral structured content.
- Format plans and renderers: target-specific implementation.

## Consistency

HTML, DOCX, and PPTX may differ in structure and density, but must agree on facts, scope, uncertainty, and release constraints.

## CLI

```powershell
python scripts/sa.py report init|validate|document|build|register|status|archive ...
python scripts/sa.py deck validate|build|preview ...
python scripts/sa.py output apply|status|lint ...
```

## Release boundary

Output registration is not publication. Packaging into `publish/packed/` requires an explicit user request. Retiring development history uses `sa report archive`.
