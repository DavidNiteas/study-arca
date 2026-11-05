# 15 · Workspaces and Programs

[中文](../15-工作区身份工单与方言.md) | English

## Workspace identity

`project.json` declares `sa.workspace/1` and one of:

- `research`;
- `synthesis`.

Identity is data, not path inference.

## Ownership

Every work order, material, reference, output, and snapshot belongs to a Workspace. Cross-workspace facts are materialized into `references/`; authority remains with the original Workspace.

## Program

Program is a fact-free Git superproject:

- members live under `nodes/<id>/`;
- `.gitmodules` records source locations;
- a gitlink pins each member commit;
- cloneable status requires every remote and pin to be reachable.

Programs are created outside the product checkout. Resolution order:

1. `--program`;
2. `SA_PROGRAM_ROOT`;
3. nearest ancestor `program.json`;
4. legacy product-local `work-root/` or `workspace/`.

`sa new --program <path>` creates the Workspace under `<program>/nodes` and attaches it as a child.

`--root` and `--program` are mutually exclusive. `--root` selects only a low-level Workspace container and does not create Program ownership.

## Provided material

Files in `brief/inbox/` are pending. Registration through `sa input add` copies them into `brief/provided/u-NNNN/` and records authority, verification state, and hash.

## Dialects

Project-specific preferences stay in the Workspace dialect. User preferences stay in the local user dialect. Only a reusable general capability should be promoted to the product core.
