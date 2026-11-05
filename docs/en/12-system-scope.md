# 12 · System Scope

[中文](../12-系统定位与能力管理.md) | English

Study Arca is a human-agent research collaboration system. Its unit of value is a self-contained Workspace that another agent can understand and continue after migration.

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
