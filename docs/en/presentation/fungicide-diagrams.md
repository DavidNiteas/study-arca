# Observed Case: From Grid to Diagram

[中文](../../presentation/fungicide-diagrams.md) | English

## Problem

The original deck relied on repeated card grids. The user asked for diagrams that preserved necessary lookup tables while showing mechanisms and evidence relationships.

## Changes

- Replace generic research cards with a reading path from application to molecule to field evidence.
- Keep codes in a mechanism-oriented branch diagram instead of a long flat table.
- Show molecular structure and mechanism location rather than adjacent explanatory paragraphs.
- Separate field observations from laboratory evidence.
- Show composition and ratios directly; node area does not encode potency.
- Use symmetric branches for alternatives without implying priority.

## Visual-review findings

Initial overflow checks were clean, but the rendered images showed crowded labels and a line crossing a label. After moving labels and shortening lines, a later review found an inhibitor marker pointing to an ambiguous target. The marker was moved so the semantic relationship was clear.

## Transferable lesson

- Choose form from the information relationship.
- Consistency helps comparison; repetition that erases difference does not.
- Machine overflow checks do not replace reading the images.
- The number of redesigned pages is not a target.

## Boundary

This is a bounded teaching case. It does not prove the same approach for every topic or audience and did not receive independent review.
