"""User-local dialect initialization."""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from .project import ProjectError, load_json, save_json


SCHEMA = "sa.dialect/1"


def validate_dialect(data: dict, *, expected_scope: str | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return [f"dialect schema 必须是 {SCHEMA}"]
    if data.get("scope") not in {"user", "workspace"}:
        errors.append("dialect scope 必须是 user/workspace")
    if expected_scope and data.get("scope") != expected_scope:
        errors.append(f"dialect scope 必须是 {expected_scope}")
    for field in ("id", "version"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            errors.append(f"dialect 缺少 {field}")
    for field in ("capabilities", "imports"):
        if not isinstance(data.get(field), list):
            errors.append(f"dialect {field} 必须是数组")
    return errors


def init_user_dialect(root: Path | str) -> Path:
    root = Path(root).resolve()
    target = root / "dialect"
    template = root / "templates/dialect"
    if target.exists():
        raise ProjectError(f"用户方言已存在：{target}")
    if not template.is_dir():
        raise ProjectError(f"缺少方言模板：{template}")
    shutil.copytree(template, target)
    return target


def dialect_status(root: Path | str, workspace: Path | str | None = None) -> dict:
    root = Path(root).resolve()
    result: dict = {
        "schema": "sa.dialect-status/1",
        "user": None,
        "workspace": None,
        "resolution_order": [
            "core-defaults",
            "user",
            "workspace",
            "core-invariants",
        ],
    }
    user_path = root / "dialect/dialect.json"
    if user_path.is_file():
        data = load_json(user_path, {}) or {}
        errors = validate_dialect(data, expected_scope="user")
        result["user"] = {"path": str(user_path), "errors": errors, "id": data.get("id")}
    if workspace is not None:
        workspace = Path(workspace).resolve()
        workspace_path = workspace / "dialect/dialect.json"
        if workspace_path.is_file():
            data = load_json(workspace_path, {}) or {}
            errors = validate_dialect(data, expected_scope="workspace")
            result["workspace"] = {
                "path": str(workspace_path),
                "errors": errors,
                "id": data.get("id"),
                "imports": data.get("imports", []),
            }
    return result


def import_dialect(workspace: Path | str, source: Path | str) -> Path:
    workspace = Path(workspace).resolve()
    source = Path(source).resolve()
    data = load_json(source, None)
    if not isinstance(data, dict):
        raise ProjectError(f"无法读取方言：{source}")
    errors = validate_dialect(data)
    if errors:
        raise ProjectError("\n".join(errors))
    workspace_file = workspace / "dialect/dialect.json"
    workspace_data = load_json(workspace_file, None)
    if not isinstance(workspace_data, dict):
        raise ProjectError("工作区缺少 dialect/dialect.json")
    errors = validate_dialect(workspace_data, expected_scope="workspace")
    if errors:
        raise ProjectError("\n".join(errors))
    import_id = data["id"]
    target = workspace / "dialect/imports" / f"{import_id}.json"
    if target.exists():
        raise ProjectError(f"工作区已导入同名方言：{import_id}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    workspace_data.setdefault("imports", []).append({
        "id": import_id,
        "path": target.relative_to(workspace / "dialect").as_posix(),
        "sha256": digest,
    })
    save_json(workspace_file, workspace_data)
    return target


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def promote_dialect(
    root: Path | str,
    workspace: Path | str,
    *,
    scope: str,
    output: Path | str | None = None,
) -> Path:
    root = Path(root).resolve()
    workspace = Path(workspace).resolve()
    source = workspace / "dialect"
    if scope not in {"user", "core"}:
        raise ProjectError("dialect promote scope 必须是 user/core")
    data = load_json(source / "dialect.json", None)
    if not isinstance(data, dict):
        raise ProjectError("工作区缺少 dialect/dialect.json")
    errors = validate_dialect(data, expected_scope="workspace")
    if errors:
        raise ProjectError("\n".join(errors))
    dialect_id = data["id"]
    if scope == "user":
        user_file = root / "dialect/dialect.json"
        if not user_file.is_file():
            raise ProjectError("用户方言尚未初始化；先运行 sa dialect init")
        target = root / "dialect/imports" / dialect_id
        if target.exists():
            raise ProjectError(f"用户方言已存在同名导入：{dialect_id}")
        shutil.copytree(source, target)
        user_data = load_json(user_file, {}) or {}
        user_data.setdefault("imports", []).append({
            "id": dialect_id,
            "source_workspace": workspace.name,
            "path": target.relative_to(root).as_posix(),
            "sha256": hashlib.sha256((target / "dialect.json").read_bytes()).hexdigest(),
        })
        save_json(user_file, user_data)
        return target

    if output is None:
        raise ProjectError("Core 晋升提案需要 --output")
    output = Path(output).resolve()
    if output.exists():
        raise ProjectError(f"提案目录已存在：{output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".sa-dialect-proposal-", dir=output.parent))
    try:
        shutil.copytree(source, temp / "dialect")
        save_json(temp / "proposal.json", {
            "schema": "sa.dialect-proposal/1",
            "id": dialect_id,
            "source_workspace": workspace.name,
            "scope": "core",
            "status": "draft",
            "requires": data.get("requires", {}),
            "files": _tree_hashes(temp / "dialect"),
            "note": "晋升提案不会自动进入发布核心；需开发工单、去个人化整理、测试和经理终审。",
        })
        temp.rename(output)
        return output
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise
