# 03 · Evidence and Traceability

[中文](../03-证据与溯源.md) | English

## Evidence grades

- `E1`: primary or authoritative source.
- `E2`: credible secondary source with identifiable origin.
- `E3`: indirect or weak support.
- `E4`: unsupported or only a lead.

## Source envelope

A source records its ID, title, publisher, date, URL/locator, evidence grade, source type, retrieval time, license, and extracted text.

## Claims

Each claim records:

- a stable ID and concise statement;
- status and confidence;
- source references;
- reasoning or scope conditions;
- conflicts and supersession relationships.

## Facts and conflicts

`facts.json` stores frozen numbers used in finished output. `conflicts.json` preserves incompatible evidence and the reason it remains unresolved.

## Confidence

Confidence reflects source quality, independence, recency, directness, consistency, and precision. It does not imply that a source is true.

## Validation

`sa lint` checks missing metadata, dangling evidence references, duplicate IDs, status inconsistencies, active conflicts, and report-to-ledger consistency. Gate waivers require an explicit reason and expiry.

Any content problem returns to the research source layer. Visual polish cannot repair an unsupported claim.
