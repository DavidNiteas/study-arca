"""Workspace identity, work orders, provided inputs, references and dialect."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path, PurePosixPath

from .project import ProjectError, load_json, save_json


SCHEMA = "sa.workspace/1"
WORKSPACE_TYPES = {"research", "synthesis"}
WORKFLOW_BY_TYPE = {
    "research": "sa.research/1",
    "synthesis": "sa.synthesis/1",
}

COMMON_DIRS = [
    "brief",
    "brief/provided",
    "dialect",
    "references",
    "work-orders",
    "report",
    "outputs",
    "deliverables/report",
    "deliverables/deck",
    "publish",
    "publish/packed",
]
RESEARCH_DIRS = [
    "search",
    "tools",
    "analysis/datasets",
    "analysis/notes",
    "analysis/findings",
    "analysis/research-ir",
    "research",
]
SYNTHESIS_DIRS = [
    "work-model",
    "synthesis",
]
LEGACY_DIRS = [
    "brief",
    "_dev",
    "search",
    "tools",
    "analysis/datasets",
    "analysis/notes",
    "analysis/findings",
    "analysis/research-ir",
    "report",
    "outputs",
    "publish",
    "publish/packed",
    "deliverables/report",
    "deliverables/deck",
]

WORK_ORDER_SCHEMA = "sa.work-order/1"
WORK_ORDER_ID_RE = re.compile(r"^wo-\d{4}$")
WORK_ORDER_STATUS = {"proposed", "active", "paused", "done", "archived"}

PROVIDED_SCHEMA = "sa.provided-inputs/1"
PROVIDED_ROLES = {"constraint", "context", "work_record", "evidence", "hypothesis"}
PROVIDED_AUTHORITY = {"binding", "first_person", "contextual"}
PROVIDED_VERIFICATION = {
    "self_reported",
    "document_supported",
    "externally_verified",
    "unknown",
}

REFERENCES_SCHEMA = "sa.references/1"
REFERENCE_SCHEMA = "sa.reference/1"
REFERENCE_RELATIONS = {
    "context_from",
    "evidence_from",
    "derived_from",
    "supersedes",
    "related_to",
}
REFERENCE_TYPES = {"research", "synthesis", "legacy"}
GIT_HASH_RE = re.compile(r"^[0-9a-f]{40,64}$")

DIALECT_SCHEMA = "sa.dialect/1"


def required_dirs(workspace_type: str, *, modern: bool) -> list[str]:
    if not modern:
        return list(LEGACY_DIRS)
    if workspace_type == "research":
        return COMMON_DIRS + RESEARCH_DIRS
    if workspace_type == "synthesis":
        return COMMON_DIRS + SYNTHESIS_DIRS
    return list(COMMON_DIRS)


def infer_workspace_type(meta: dict) -> str | None:
    declared = meta.get("workspace_type")
    if declared in WORKSPACE_TYPES:
        return declared
    if meta.get("workflow") == "sa.research/1":
        return "research"
    if meta.get("workflow") == "sa.synthesis/1":
        return "synthesis"
    return None


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inside(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ProjectError(f"文件不存在或越出目录：{value}")
    return path


def load_work_orders(project: Path | str) -> list[dict]:
    project = Path(project)
    directory = project / "work-orders"
    orders: list[dict] = []
    for path in sorted(directory.glob("wo-*.json")) if directory.is_dir() else []:
        try:
            order = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise ProjectError(f"无法读取工单 {path.name}: {exc}") from exc
        if not isinstance(order, dict):
            raise ProjectError(f"工单必须是 JSON 对象：{path.name}")
        orders.append(order)
    return orders


def _validate_work_orders(project: Path, owner: str, errors: list[str]) -> None:
    seen: set[str] = set()
    directory = project / "work-orders"
    for path in sorted(directory.glob("wo-*.json")) if directory.is_dir() else []:
        try:
            order = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            errors.append(f"工单不是合法 JSON：{path.name}: {exc}")
            continue
        if not isinstance(order, dict):
            errors.append(f"工单必须是对象：{path.name}")
            continue
        order_id = order.get("id")
        if not isinstance(order_id, str) or not WORK_ORDER_ID_RE.fullmatch(order_id):
            errors.append(f"工单 id 非法：{path.name}")
            continue
        if order_id in seen:
            errors.append(f"工单 id 重复：{order_id}")
        seen.add(order_id)
        if path.stem != order_id:
            errors.append(f"工单文件名与 id 不一致：{path.name}")
        if order.get("schema") != WORK_ORDER_SCHEMA:
            errors.append(f"{order_id}.schema 必须是 {WORK_ORDER_SCHEMA}")
        if order.get("owner_workspace") != owner:
            errors.append(f"{order_id}.owner_workspace 必须是 {owner}")
        if order.get("status") not in WORK_ORDER_STATUS:
            errors.append(f"{order_id}.status 非法")
        for field in ("title", "goal"):
            if not isinstance(order.get(field), str) or not order[field].strip():
                errors.append(f"{order_id}.{field} 必须是非空文本")
        try:
            datetime.fromisoformat(str(order.get("created", "")))
        except ValueError:
            errors.append(f"{order_id}.created 必须是 ISO 日期")
        for field in ("scope", "acceptance", "references"):
            if not isinstance(order.get(field), list):
                errors.append(f"{order_id}.{field} 必须是数组")
        reference_manifests = _reference_manifests(project)
        for index, reference in enumerate(order.get("references", [])):
            mark = f"{order_id}.references[{index}]"
            if not isinstance(reference, dict):
                errors.append(f"{mark} 必须是对象")
                continue
            target_workspace = reference.get("workspace")
            target_order = reference.get("order")
            relation = reference.get("relation")
            if not isinstance(target_workspace, str) or not target_workspace.strip():
                errors.append(f"{mark}.workspace 必须是非空文本")
                continue
            if not isinstance(target_order, str) or not WORK_ORDER_ID_RE.fullmatch(target_order):
                errors.append(f"{mark}.order 必须是 wo-NNNN")
            if relation not in REFERENCE_RELATIONS:
                errors.append(f"{mark}.relation 非法")
            if target_workspace == owner:
                if not (project / "work-orders" / f"{target_order}.json").is_file():
                    errors.append(f"{mark} 引用了不存在的本地工单：{target_order}")
            else:
                expected_source = f"work-orders/{target_order}.json"
                if not any(
                    item.get("target_workspace") == target_workspace
                    and item.get("source_path") == expected_source
                    and item.get("relation") == relation
                    for item in reference_manifests
                ):
                    errors.append(f"{mark} 未在 references/ 中物化跨工作区工单：{target_workspace}/{target_order}")


def create_work_order(
    project: Path | str,
    title: str,
    goal: str,
    *,
    status: str = "proposed",
) -> Path:
    project = Path(project)
    meta = load_json(project / "project.json", {}) or {}
    owner = meta.get("id")
    if not owner:
        raise ProjectError("不是有效工作区")
    if not title.strip() or not goal.strip():
        raise ProjectError("工单 title 和 goal 不能为空")
    if status not in WORK_ORDER_STATUS:
        raise ProjectError(f"工单 status 必须是 {sorted(WORK_ORDER_STATUS)}")
    directory = project / "work-orders"
    directory.mkdir(parents=True, exist_ok=True)
    numbers = [int(path.stem.split("-")[1]) for path in directory.glob("wo-*.json")
               if WORK_ORDER_ID_RE.fullmatch(path.stem)]
    order_id = f"wo-{max(numbers, default=0) + 1:04d}"
    path = directory / f"{order_id}.json"
    save_json(path, {
        "schema": WORK_ORDER_SCHEMA,
        "id": order_id,
        "owner_workspace": owner,
        "title": title.strip(),
        "status": status,
        "created": datetime.now().astimezone().date().isoformat(),
        "goal": goal.strip(),
        "scope": [],
        "acceptance": [],
        "references": [],
    })
    return path


def set_work_order_status(project: Path | str, order_id: str, status: str) -> Path:
    project = Path(project)
    if status not in WORK_ORDER_STATUS:
        raise ProjectError(f"工单 status 必须是 {sorted(WORK_ORDER_STATUS)}")
    if not WORK_ORDER_ID_RE.fullmatch(order_id):
        raise ProjectError("工单 id 格式非法")
    path = project / "work-orders" / f"{order_id}.json"
    if not path.is_file():
        raise ProjectError(f"工单不存在：{order_id}")
    order = load_json(path, {}) or {}
    meta = load_json(project / "project.json", {}) or {}
    if order.get("owner_workspace") != meta.get("id"):
        raise ProjectError("工单 owner_workspace 与当前工作区不一致")
    order["status"] = status
    save_json(path, order)
    return path


def _validate_provided(project: Path, errors: list[str]) -> None:
    root = project / "brief/provided"
    manifest = root / "manifest.json"
    if not manifest.is_file():
        errors.append("缺少 brief/provided/manifest.json")
        return
    try:
        data = json.loads(manifest.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        errors.append(f"用户材料清单不是合法 JSON：{exc}")
        return
    if not isinstance(data, dict) or data.get("schema") != PROVIDED_SCHEMA:
        errors.append(f"用户材料清单 schema 必须是 {PROVIDED_SCHEMA}")
        return
    items = data.get("items")
    if not isinstance(items, list):
        errors.append("用户材料清单 items 必须是数组")
        return
    seen: set[str] = set()
    for index, item in enumerate(items):
        mark = f"brief/provided/items[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{mark} 必须是对象")
            continue
        item_id = item.get("id")
        expected = re.compile(r"^u-\d{4}$")
        if not isinstance(item_id, str) or not expected.fullmatch(item_id) or item_id in seen:
            errors.append(f"{mark}.id 非法或重复")
            continue
        seen.add(item_id)
        if item.get("role") not in PROVIDED_ROLES:
            errors.append(f"{mark}.role 非法")
        if item.get("authority") not in PROVIDED_AUTHORITY:
            errors.append(f"{mark}.authority 非法")
        if item.get("verification") not in PROVIDED_VERIFICATION:
            errors.append(f"{mark}.verification 非法")
        try:
            path = _inside(root, str(item.get("path", "")))
        except ProjectError as exc:
            errors.append(f"{mark}: {exc}")
            continue
        expected_hash = item.get("sha256")
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            errors.append(f"{mark}.sha256 非法")
        elif _digest(path) != expected_hash:
            errors.append(f"{mark}.sha256 与文件不一致")


def add_provided_input(
    project: Path | str,
    source: Path | str,
    *,
    role: str,
    authority: str,
    verification: str,
) -> tuple[Path, dict]:
    project = Path(project).resolve()
    source = Path(source).resolve()
    if role not in PROVIDED_ROLES:
        raise ProjectError(f"用户材料 role 必须是 {sorted(PROVIDED_ROLES)}")
    if authority not in PROVIDED_AUTHORITY:
        raise ProjectError(f"用户材料 authority 必须是 {sorted(PROVIDED_AUTHORITY)}")
    if verification not in PROVIDED_VERIFICATION:
        raise ProjectError(f"用户材料 verification 必须是 {sorted(PROVIDED_VERIFICATION)}")
    if not source.is_file():
        raise ProjectError(f"用户材料不存在：{source}")

    root = project / "brief/provided"
    manifest_path = root / "manifest.json"
    manifest = load_json(manifest_path, {
        "schema": PROVIDED_SCHEMA,
        "items": [],
    }) or {}
    if manifest.get("schema") != PROVIDED_SCHEMA or not isinstance(manifest.get("items"), list):
        raise ProjectError("用户材料清单格式非法")
    numbers = []
    for item in manifest["items"]:
        item_id = item.get("id", "") if isinstance(item, dict) else ""
        match = re.fullmatch(r"u-(\d{4})", item_id)
        if match:
            numbers.append(int(match.group(1)))
    item_id = f"u-{max(numbers, default=0) + 1:04d}"
    destination_dir = root / item_id
    if destination_dir.exists():
        raise ProjectError(f"用户材料目录已存在：{destination_dir}")
    destination_dir.mkdir(parents=True)
    destination = destination_dir / source.name
    try:
        shutil.copy2(source, destination)
        item = {
            "id": item_id,
            "path": destination.relative_to(root).as_posix(),
            "role": role,
            "authority": authority,
            "verification": verification,
            "sha256": _digest(destination),
        }
        manifest["items"].append(item)
        save_json(manifest_path, manifest)
    except Exception:
        destination.unlink(missing_ok=True)
        destination_dir.rmdir()
        raise
    return destination, item


def _validate_references(project: Path, errors: list[str]) -> None:
    path = project / "references/index.json"
    if not path.is_file():
        errors.append("缺少 references/index.json")
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        errors.append(f"引用索引不是合法 JSON：{exc}")
        return
    if not isinstance(data, dict) or data.get("schema") != REFERENCES_SCHEMA:
        errors.append(f"引用索引 schema 必须是 {REFERENCES_SCHEMA}")
        return
    references = data.get("references")
    if not isinstance(references, list):
        errors.append("引用索引 references 必须是数组")
        return
    seen: set[str] = set()
    reference_root = project / "references"
    for index, item in enumerate(references):
        mark = f"references[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{mark} 必须是对象")
            continue
        ref_id = item.get("id")
        if not isinstance(ref_id, str) or not re.fullmatch(r"ref-\d{4}", ref_id) or ref_id in seen:
            errors.append(f"{mark}.id 非法或重复")
            continue
        seen.add(ref_id)
        try:
            manifest = json.loads(
                _inside(reference_root, str(item.get("path", ""))).read_text(encoding="utf-8-sig")
            )
        except ProjectError as exc:
            errors.append(f"{mark}: {exc}")
            continue
        except (OSError, ValueError) as exc:
            errors.append(f"{mark}.path 不是合法引用 manifest：{exc}")
            continue
        if not isinstance(manifest, dict) or manifest.get("schema") != REFERENCE_SCHEMA:
            errors.append(f"{mark}.schema 必须是 {REFERENCE_SCHEMA}")
            continue
        if manifest.get("id") != ref_id:
            errors.append(f"{mark}.id 与引用 manifest 不一致")
        if manifest.get("relation") not in REFERENCE_RELATIONS:
            errors.append(f"{mark}.relation 非法")
        if not isinstance(manifest.get("target_workspace"), str) or not manifest["target_workspace"].strip():
            errors.append(f"{mark}.target_workspace 必须是非空文本")
        if manifest.get("target_type") not in REFERENCE_TYPES:
            errors.append(f"{mark}.target_type 非法")
        if "target_commit" not in manifest:
            errors.append(f"{mark}.target_commit 字段缺失")
        elif manifest["target_commit"] is not None and not (
            isinstance(manifest["target_commit"], str)
            and GIT_HASH_RE.fullmatch(manifest["target_commit"])
        ):
            errors.append(f"{mark}.target_commit 非法")
        for field in ("artifact_id", "source_path", "copied_path"):
            if not isinstance(manifest.get(field), str) or not manifest[field].strip():
                errors.append(f"{mark}.{field} 必须是非空文本")
        source_path = manifest.get("source_path")
        if isinstance(source_path, str):
            source_parts = PurePosixPath(source_path).parts
            if PurePosixPath(source_path).is_absolute() or ".." in source_parts:
                errors.append(f"{mark}.source_path 必须是来源工作区相对路径")
        for field in ("source_sha256", "copied_sha256"):
            value = manifest.get(field)
            if not isinstance(value, str) or len(value) != 64 or not re.fullmatch(r"[0-9a-f]{64}", value):
                errors.append(f"{mark}.{field} 非法")
        if manifest.get("source_sha256") != manifest.get("copied_sha256"):
            errors.append(f"{mark} 的源哈希与副本哈希不一致")
        try:
            captured = datetime.fromisoformat(str(manifest.get("captured_at", "")))
            if captured.tzinfo is None:
                raise ValueError()
        except (TypeError, ValueError):
            errors.append(f"{mark}.captured_at 必须是带时区 ISO 时间")
        copied_path = manifest.get("copied_path")
        if isinstance(copied_path, str) and not copied_path.startswith(f"{ref_id}/payload/"):
            errors.append(f"{mark}.copied_path 必须位于 {ref_id}/payload/")
        try:
            payload = _inside(reference_root, str(copied_path or ""))
        except ProjectError as exc:
            errors.append(f"{mark}: {exc}")
            continue
        copied_hash = manifest.get("copied_sha256")
        if not isinstance(copied_hash, str) or len(copied_hash) != 64 or _digest(payload) != copied_hash:
            errors.append(f"{mark}.copied_sha256 缺失或不一致")


def validate_references(project: Path | str) -> list[str]:
    errors: list[str] = []
    _validate_references(Path(project), errors)
    return errors


def _reference_manifests(project: Path) -> list[dict]:
    index = load_json(project / "references/index.json", {}) or {}
    manifests = []
    for entry in index.get("references", []):
        if not isinstance(entry, dict):
            continue
        path = project / "references" / str(entry.get("path", ""))
        if path.is_file():
            try:
                manifest = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                continue
            if isinstance(manifest, dict):
                manifests.append(manifest)
    return manifests


def verify_reference_authorities(project: Path | str, search_root: Path | str) -> list[dict]:
    project = Path(project).resolve()
    search_root = Path(search_root).resolve()
    workspaces: dict[str, Path] = {}
    for meta_path in search_root.rglob("project.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if isinstance(meta, dict) and isinstance(meta.get("id"), str):
            if meta["id"] in workspaces and workspaces[meta["id"]] != meta_path.parent:
                raise ProjectError(f"扫描到重复 workspace ID：{meta['id']}")
            workspaces[meta["id"]] = meta_path.parent
    results = []
    for manifest in _reference_manifests(project):
        target = workspaces.get(manifest.get("target_workspace"))
        current_commit = None
        if target is not None:
            head = subprocess.run(
                ["git", "-C", str(target), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if head.returncode == 0:
                current_commit = head.stdout.strip()
        pinned = manifest.get("target_commit")
        source_hash = None
        if target is not None:
            source_path = target / str(manifest.get("source_path", ""))
            if source_path.is_file():
                source_hash = _digest(source_path)
        if target is None:
            state = "authority_unavailable"
        elif source_hash is None:
            state = "authority_unavailable"
        elif source_hash != manifest.get("source_sha256"):
            state = "authority_changed"
        elif pinned is None or current_commit is None:
            state = "authority_unversioned"
        elif pinned == current_commit:
            state = "current"
        else:
            state = "authority_changed"
        results.append({
            "id": manifest.get("id"),
            "target_workspace": manifest.get("target_workspace"),
            "target_commit": pinned,
            "current_commit": current_commit,
            "current_source_sha256": source_hash,
            "authority_state": state,
        })
    return results


def add_reference(
    consumer: Path | str,
    source_workspace: Path | str,
    artifact: Path | str,
    *,
    relation: str,
    artifact_id: str | None = None,
) -> tuple[Path, dict]:
    consumer = Path(consumer).resolve()
    source_workspace = Path(source_workspace).resolve()
    if relation not in REFERENCE_RELATIONS:
        raise ProjectError(f"引用 relation 必须是 {sorted(REFERENCE_RELATIONS)}")
    source_meta = load_json(source_workspace / "project.json", None)
    if not isinstance(source_meta, dict) or not source_meta.get("id"):
        raise ProjectError("来源必须是有效 workspace")
    source_type = infer_workspace_type(source_meta)
    artifact = Path(artifact).resolve()
    if not artifact.is_file():
        raise ProjectError(f"来源材料不存在：{artifact}")
    if not artifact.is_relative_to(source_workspace):
        raise ProjectError("来源材料必须位于来源工作区")
    source_relative = artifact.relative_to(source_workspace).as_posix()
    allowed_roots = ("publish/", "deliverables/", "research/artifacts/", "work-orders/")
    if not source_relative.startswith(allowed_roots):
        raise ProjectError(
            "引用材料必须来自来源工作区的 publish/、deliverables/、research/artifacts/ 或 work-orders/"
        )
    consumer_meta = load_json(consumer / "project.json", {}) or {}
    if not consumer_meta.get("id"):
        raise ProjectError("消费者必须是有效 workspace")
    if source_meta["id"] == consumer_meta["id"]:
        raise ProjectError("引用来源不能是当前工作区自身")
    source_hash = _digest(artifact)
    commit = None
    top = subprocess.run(
        ["git", "-C", str(source_workspace), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if top.returncode == 0 and Path(top.stdout.strip()).resolve() == source_workspace:
        tracked = subprocess.run(
            ["git", "-C", str(source_workspace), "ls-files", "--error-unmatch", "--", source_relative],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if tracked.returncode != 0:
            raise ProjectError("Git 来源材料必须已纳入来源工作区版本")
        dirty = subprocess.run(
            [
                "git",
                "-C",
                str(source_workspace),
                "status",
                "--porcelain",
                "--untracked-files=all",
                "--",
                source_relative,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if dirty.returncode != 0:
            raise ProjectError(dirty.stderr.strip() or "无法检查来源材料状态")
        if dirty.stdout.strip():
            raise ProjectError("来源材料存在未提交修改，不能作为正式引用")
        head = subprocess.run(
            ["git", "-C", str(source_workspace), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if head.returncode == 0:
            commit = head.stdout.strip()

    reference_root = consumer / "references"
    index_path = reference_root / "index.json"
    index = load_json(index_path, {"schema": REFERENCES_SCHEMA, "references": []}) or {}
    if index.get("schema") != REFERENCES_SCHEMA or not isinstance(index.get("references"), list):
        raise ProjectError("引用索引格式非法")
    numbers = []
    for item in index["references"]:
        match = re.fullmatch(r"ref-(\d{4})", item.get("id", "")) if isinstance(item, dict) else None
        if match:
            numbers.append(int(match.group(1)))
    ref_id = f"ref-{max(numbers, default=0) + 1:04d}"
    ref_dir = reference_root / ref_id
    if ref_dir.exists():
        raise ProjectError(f"引用目录已存在：{ref_dir}")
    payload_dir = ref_dir / "payload"
    payload_dir.mkdir(parents=True)
    copied = payload_dir / artifact.name
    try:
        shutil.copy2(artifact, copied)
        manifest = {
            "schema": REFERENCE_SCHEMA,
            "id": ref_id,
            "target_workspace": source_meta["id"],
            "target_type": source_type or "legacy",
            "target_commit": commit,
            "artifact_id": artifact_id or source_relative,
            "source_path": source_relative,
            "source_sha256": source_hash,
            "copied_path": copied.relative_to(reference_root).as_posix(),
            "copied_sha256": _digest(copied),
            "relation": relation,
            "captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "authority_state": "captured",
        }
        save_json(ref_dir / "manifest.json", manifest)
        index["references"].append({
            "id": ref_id,
            "path": f"{ref_id}/manifest.json",
        })
        save_json(index_path, index)
    except Exception:
        shutil.rmtree(ref_dir, ignore_errors=True)
        raise
    return ref_dir, manifest


def _validate_dialect(project: Path, errors: list[str]) -> None:
    path = project / "dialect/dialect.json"
    if not path.is_file():
        errors.append("缺少 dialect/dialect.json")
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        errors.append(f"工作区方言不是合法 JSON：{exc}")
        return
    if not isinstance(data, dict) or data.get("schema") != DIALECT_SCHEMA:
        errors.append(f"工作区方言 schema 必须是 {DIALECT_SCHEMA}")
        return
    if data.get("scope") != "workspace":
        errors.append("工作区 dialect.json 的 scope 必须是 workspace")
    for field in ("id", "version"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            errors.append(f"工作区方言缺少 {field}")
    for field in ("capabilities", "imports"):
        if not isinstance(data.get(field), list):
            errors.append(f"工作区方言 {field} 必须是数组")
    for index, item in enumerate(data.get("imports", [])):
        mark = f"工作区方言 imports[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{mark} 必须是对象")
            continue
        if not isinstance(item.get("id"), str) or not item["id"].strip():
            errors.append(f"{mark}.id 必须是非空文本")
        try:
            path = _inside(project / "dialect", str(item.get("path", "")))
        except ProjectError as exc:
            errors.append(f"{mark}: {exc}")
            continue
        expected = item.get("sha256")
        if not isinstance(expected, str) or len(expected) != 64 or _digest(path) != expected:
            errors.append(f"{mark}.sha256 缺失或不一致")


def validate_workspace(project: Path | str, meta: dict) -> tuple[list[str], list[str]]:
    project = Path(project)
    errors: list[str] = []
    warnings: list[str] = []
    schema = meta.get("schema")
    modern = schema == SCHEMA
    if schema not in (None, SCHEMA):
        errors.append(f"未知 workspace schema：{schema}")
        return errors, warnings
    declared_type = meta.get("workspace_type")
    if declared_type is not None and declared_type not in WORKSPACE_TYPES:
        errors.append(f"未知 workspace_type：{declared_type}")
        return errors, warnings
    if schema is None and declared_type == "synthesis":
        errors.append("synthesis 工作区必须声明 sa.workspace/1")
        return errors, warnings
    workspace_type = infer_workspace_type(meta)
    if modern:
        if workspace_type not in WORKSPACE_TYPES:
            errors.append("现代 workspace 必须声明 research/synthesis 类型")
            return errors, warnings
        expected_workflow = WORKFLOW_BY_TYPE[workspace_type]
        if meta.get("workflow") != expected_workflow:
            errors.append(f"{workspace_type} workspace 的 workflow 必须是 {expected_workflow}")
        for rel in required_dirs(workspace_type, modern=True):
            if not (project / rel).is_dir():
                errors.append(f"缺少目录：{rel}")
        _validate_work_orders(project, meta.get("id", ""), errors)
        _validate_provided(project, errors)
        _validate_references(project, errors)
        _validate_dialect(project, errors)
    elif workspace_type is None:
        # Legacy projects remain readable without adding recurring lint noise.
        pass
    return errors, warnings


def workspace_status(project: Path | str) -> dict:
    project = Path(project)
    meta = load_json(project / "project.json", {}) or {}
    orders = load_work_orders(project)
    provided = load_json(project / "brief/provided/manifest.json", {"items": []}) or {}
    references = load_json(project / "references/index.json", {"references": []}) or {}
    return {
        "schema": meta.get("schema"),
        "workspace_type": infer_workspace_type(meta),
        "workflow": meta.get("workflow"),
        "work_orders": len(orders),
        "work_orders_open": sum(
            order.get("status") in {"proposed", "active", "paused"} for order in orders
        ),
        "provided_inputs": len(provided.get("items", [])),
        "references": len(references.get("references", [])),
    }
