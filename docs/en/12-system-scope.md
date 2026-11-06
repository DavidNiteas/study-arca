# 12 · System Scope

[中文](../12-系统定位与能力管理.md) | English

Study Arca is a human-agent research collaboration system. Its unit of value is a self-contained Workspace that another agent can understand and continue after migration.

## Product form: the agent application is the frontend

Study Arca adopts a new software form. It does not require a dedicated desktop, web IDE, or chat interface as its frontend. Instead, it uses general-purpose agent applications such as Codex or Claude Code for natural-language interaction, file access, command execution, and tool use.

```text
Human ↔ general-purpose agent ↔ Study Arca protocols, skills, and sa control plane ↔ Program / Workspace / outputs
```

In this division:

- humans define goals, authorize scope, and review results;
- the general-purpose agent is the interaction frontend and execution environment;
- Study Arca supplies checkable protocols, deterministic tools, state, and validation;
- Programs and Workspaces preserve portable ownership, facts, and outputs;
- skills are one agent entry form, not the definition of Study Arca.

Study Arca therefore neither requires humans to drive every CLI command directly nor fixes a specific model or vendor as a product dependency. In normal use, humans state an outcome in natural language; the agent follows repository specifications and skills; and `sa` turns critical actions into repeatable, verifiable machine operations.

## Division of responsibility

- Workflow specifications define research behavior.
- Agent skills route tasks and enforce minimum checks.
- CLI and code provide repeatable operations.
- Environment records capture actual renderer, font, model, and image-reading capability.
- Program is a thin graph of Workspaces and commit pins.

## Capability states

Distinguish:

- integrated public tool;
- project-level validated adaptation;
- unavailable or unverified capability.

Record dependencies, validation time, entry point, failure mode, and fallback. A single successful run does not prove universal support.

## Boundary

The product does not ship a default Program. Research data remains outside product Git history. Core PPTX compilation does not depend on PowerPoint COM; actual visual acceptance still depends on a target renderer.
