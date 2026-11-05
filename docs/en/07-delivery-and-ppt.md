# 07 · Delivery and Presentations

[中文](../07-交付与PPT.md) | English

## Delivery chain

```text
Frozen research inputs
→ ReportPlan / ContentMap / NarrativePlan
→ ReportDocument
→ DOCX / HTML / PPTX
→ preview and review
→ deliverables/
→ publish/
```

## Formats

- HTML: self-contained evidence browsing.
- DOCX: formal report and archive.
- PPTX: live presentation with editable native objects.

## PPT

Use DeckPlan and RenderLayout. Compile with `sa deck build`, render with `sa deck preview`, inspect actual images, revise the layout, and re-render. Machine overflow checks do not replace visual review.

## Release

`publish/vX.Y/` is immutable. `publish/release/` is an exact copy of the latest release. `sa pack` creates an external delivery archive only when explicitly requested.

## Development archive

`sa report archive` retires old report development versions into `archive/reports/<report-id>/`. It first creates a verifiable ZIP and manifest, then removes source files only after hash validation.

## Git history maintenance

History rewriting requires explicit authorization. Create and verify a complete Git bundle, dry-run the path filter, rewrite, run `git fsck --strict`, preserve an old-to-new commit map, and update Program pins.
