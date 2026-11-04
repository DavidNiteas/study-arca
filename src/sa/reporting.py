"""Independent report planning, source mapping and multi-format output."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from .project import ProjectError, load_json, save_json


REPORT_PLAN_SCHEMA = "sa.report-plan/1"
REPORT_MANIFEST_SCHEMA = "sa.report-artifacts/1"
DOCUMENT_SCHEMA = "sa.document/1"
REPORT_FORMATS = {"docx", "html", "pptx"}
SOURCE_KINDS = {"snapshot", "material", "reference", "design_artifact", "alignment"}
DISPOSITIONS = {"include", "compress", "omit", "redact", "defer"}
BLOCK_TYPES = {"heading", "paragraph", "callout", "list", "table", "figure", "code"}
BLOCK_LAYERS = {"user_statement", "material", "inference", "unknown", "fact", "option"}
REPORT_ID_RE = re.compile(r"^rpt-\d{4}$")
SOURCE_ID_RE = re.compile(r"^[a-z]-\d{4}$")
SECTION_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,79}$")
CITATION_RE = re.compile(r"\[\^([a-z]-\d{4})\]")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digest_json(value) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _inside_project(project: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute():
        raise ProjectError(f"路径必须是工作区相对路径：{value}")
    path = (project / relative).resolve()
    if not path.is_relative_to(project):
        raise ProjectError(f"路径越出工作区：{value}")
    return path


def _workspace_meta(project: Path) -> dict:
    meta = load_json(project / "project.json", {}) or {}
    if not meta.get("id"):
        raise ProjectError("不是有效的 Study Arca 工作区")
    return meta


def _require_synthesis(project: Path) -> dict:
    meta = _workspace_meta(project)
    if meta.get("workspace_type") != "synthesis":
        raise ProjectError("D7 report 当前只支持 synthesis 工作区")
    return meta


def _report_root(project: Path) -> Path:
    return project / "report"


def report_dir(project: Path | str, report_id: str) -> Path:
    project = Path(project).resolve()
    _require_synthesis(project)
    if not isinstance(report_id, str) or not REPORT_ID_RE.fullmatch(report_id):
        raise ProjectError("report id 必须是 rpt-NNNN")
    return _report_root(project) / report_id


def plan_path(project: Path | str, report_id: str) -> Path:
    return report_dir(project, report_id) / "plan.json"


def manifest_path(project: Path | str, report_id: str) -> Path:
    return report_dir(project, report_id) / "manifest.json"


def document_path(project: Path | str, report_id: str) -> Path:
    return report_dir(project, report_id) / "document.json"


@contextmanager
def _writer(project: Path):
    directory = _report_root(project)
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / ".report.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise ProjectError("报告工作区正在写入；确认无写者后再处理锁") from exc
    try:
        with handle:
            handle.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _artifact_relative(project: Path, path: Path) -> str:
    path = path.resolve()
    if not path.is_relative_to(project):
        raise ProjectError("报告 artifact 必须位于工作区内")
    return path.relative_to(project).as_posix()


def _new_plan(meta: dict, report_id: str, title: str, formats: list[str]) -> dict:
    return {
        "schema": REPORT_PLAN_SCHEMA,
        "id": report_id,
        "project": meta["id"],
        "title": title,
        "as_of": date.today().isoformat(),
        "version": "v0.1",
        "formats": formats,
        "brief": {},
        "sources": [],
        "content_map": [],
        "narrative": {
            "core_question": "",
            "central_message": "",
            "angles": [],
            "sections": [],
        },
        "footnotes": {},
        "assumptions": [],
        "open_issues": [],
    }


def _new_manifest(meta: dict, report_id: str, title: str) -> dict:
    return {
        "schema": REPORT_MANIFEST_SCHEMA,
        "project": meta["id"],
        "report": report_id,
        "title": title,
        "updated_at": _now(),
        "sources": [],
        "artifacts": [],
    }


def _load_manifest(project: Path, report_id: str) -> dict:
    path = manifest_path(project, report_id)
    data = load_json(path, None)
    if not isinstance(data, dict):
        raise ProjectError(f"报告 manifest 不存在：{path}")
    if data.get("schema") != REPORT_MANIFEST_SCHEMA:
        raise ProjectError(f"报告 manifest schema 必须是 {REPORT_MANIFEST_SCHEMA}")
    if data.get("project") != _workspace_meta(project).get("id"):
        raise ProjectError("报告 manifest project 与工作区不一致")
    if data.get("report") != report_id:
        raise ProjectError("报告 manifest report 与目录 ID 不一致")
    if not isinstance(data.get("artifacts"), list):
        raise ProjectError("报告 manifest artifacts 必须是数组")
    return data


def _save_manifest(project: Path, report_id: str, data: dict) -> None:
    data["updated_at"] = _now()
    _write_json(manifest_path(project, report_id), data)


def _upsert_artifact(
    project: Path,
    report_id: str,
    *,
    artifact_id: str,
    kind: str,
    path: Path,
    format_name: str | None = None,
) -> dict:
    manifest = _load_manifest(project, report_id)
    entry = {
        "id": artifact_id,
        "kind": kind,
        "path": _artifact_relative(project, path),
        "sha256": _digest_file(path),
    }
    if format_name:
        entry["format"] = format_name
    artifacts = [
        item for item in manifest["artifacts"]
        if item.get("id") != artifact_id
    ]
    artifacts.append(entry)
    manifest["artifacts"] = artifacts
    _save_manifest(project, report_id, manifest)
    return entry


def _update_manifest_sources(project: Path, report_id: str, sources: list[dict]) -> None:
    manifest = _load_manifest(project, report_id)
    manifest["sources"] = copy.deepcopy(sources)
    _save_manifest(project, report_id, manifest)


def init_report(
    project: Path | str,
    report_id: str,
    title: str,
    *,
    formats: list[str] | None = None,
) -> Path:
    project = Path(project).resolve()
    meta = _require_synthesis(project)
    if not isinstance(title, str) or not title.strip():
        raise ProjectError("report init 需要非空 title")
    report_id = report_id.strip()
    directory = report_dir(project, report_id)
    if directory.exists():
        raise ProjectError(f"报告目录已存在：{directory}")
    selected_formats = list(dict.fromkeys(formats or sorted(REPORT_FORMATS)))
    if not selected_formats or any(value not in REPORT_FORMATS for value in selected_formats):
        raise ProjectError("report formats 必须是 docx、html、pptx 的非空子集")
    with _writer(project):
        for subdir in (directory / "plans", directory / "artifacts", directory / "previews"):
            subdir.mkdir(parents=True, exist_ok=False)
        plan_file = directory / "plan.json"
        _write_json(plan_file, _new_plan(meta, report_id, title.strip(), selected_formats))
        _write_json(
            manifest_path(project, report_id),
            _new_manifest(meta, report_id, title.strip()),
        )
    return plan_file


def load_report_plan(project: Path | str, report_id: str) -> dict:
    project = Path(project).resolve()
    path = plan_path(project, report_id)
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ProjectError(f"无法读取 ReportPlan：{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProjectError("ReportPlan 必须是 JSON 对象")
    return value


def _text_list(value, field: str, errors: list[str], mark: str, *, required=False) -> None:
    if value is None and not required:
        return
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        errors.append(f"{mark}.{field} 必须是非空文本数组")


def _validate_blocks(
    project: Path,
    blocks,
    known_refs: set[str],
    errors: list[str],
    mark: str,
) -> None:
    if not isinstance(blocks, list):
        errors.append(f"{mark}.blocks 必须是数组")
        return

    def citations(text: str, where: str) -> None:
        for ref in CITATION_RE.findall(text):
            if ref not in known_refs:
                errors.append(f"{where} 引用了未声明来源：{ref}")

    for index, block in enumerate(blocks):
        block_mark = f"{mark}.blocks[{index}]"
        if not isinstance(block, dict):
            errors.append(block_mark + " 必须是对象")
            continue
        kind = block.get("type")
        if kind not in BLOCK_TYPES:
            errors.append(block_mark + ".type 非法")
            continue
        layer = block.get("layer")
        if layer is not None and layer not in BLOCK_LAYERS:
            errors.append(block_mark + ".layer 非法")
        if kind in {"paragraph", "callout", "code", "heading"}:
            if not isinstance(block.get("text"), str) or not block["text"].strip():
                errors.append(block_mark + ".text 必须是非空文本")
            else:
                citations(block["text"], block_mark)
        if kind == "heading" and block.get("level") not in {1, 2, 3, 4}:
            errors.append(block_mark + ".level 必须是 1-4")
        if kind == "list":
            items = block.get("items")
            if not isinstance(items, list) or any(
                not isinstance(item, str) or not item.strip() for item in items
            ):
                errors.append(block_mark + ".items 必须是非空文本数组")
            else:
                for item in items:
                    citations(item, block_mark)
        if kind == "table":
            columns = block.get("columns")
            rows = block.get("rows")
            if not isinstance(columns, list) or any(
                not isinstance(item, str) for item in columns
            ):
                errors.append(block_mark + ".columns 必须是文本数组")
            if not isinstance(rows, list) or any(
                not isinstance(row, list)
                or any(not isinstance(cell, str) for cell in row)
                for row in rows
            ):
                errors.append(block_mark + ".rows 必须是二维文本数组")
            elif isinstance(rows, list):
                for row in rows:
                    for cell in row:
                        citations(cell, block_mark)
        if kind == "figure":
            src = block.get("src")
            if not isinstance(src, str) or not src.strip():
                errors.append(block_mark + ".src 必须是非空路径")
            else:
                try:
                    path = _inside_project(project, src)
                    if not path.is_file():
                        errors.append(block_mark + ".src 文件不存在")
                except ProjectError as exc:
                    errors.append(block_mark + f".src {exc}")


def _resolve_source(project: Path, source: dict) -> tuple[dict | None, list[str]]:
    errors: list[str] = []
    source_id = source.get("id")
    kind = source.get("kind")
    ref = source.get("ref")
    if not isinstance(source_id, str) or not SOURCE_ID_RE.fullmatch(source_id):
        errors.append("source.id 必须形如 s-0001")
    if kind not in SOURCE_KINDS:
        errors.append(f"source {source_id}.kind 非法")
    if not isinstance(ref, str) or not ref.strip():
        errors.append(f"source {source_id}.ref 必须是非空文本")
    if errors:
        return None, errors

    expected = source.get("sha256")
    if expected is not None and (
        not isinstance(expected, str) or not SHA256_RE.fullmatch(expected)
    ):
        errors.append(f"source {source_id}.sha256 非法")

    digest = None
    title = ref
    locator = ""
    if kind == "snapshot":
        ledger = load_json(project / "synthesis/ledger.json", {}) or {}
        record = next(
            (
                item for item in ledger.get("records", [])
                if item.get("type") == "snapshot" and item.get("id") == ref
            ),
            None,
        )
        if not record:
            errors.append(f"source {source_id} 引用了不存在的 snapshot：{ref}")
        else:
            path = (project / record["path"]).resolve()
            if not path.is_relative_to(project) or not path.is_file():
                errors.append(f"source {source_id} 的 snapshot 文件不存在")
            elif _digest_file(path) != record.get("sha256"):
                errors.append(f"source {source_id} 的 snapshot 哈希不一致")
            else:
                digest = record["sha256"]
                title = record.get("label") or ref
                locator = record.get("path", "")
    elif kind == "material":
        provided = load_json(project / "brief/provided/manifest.json", {}) or {}
        item = next(
            (
                value for value in provided.get("items", [])
                if isinstance(value, dict) and value.get("id") == ref
            ),
            None,
        )
        if not item:
            errors.append(f"source {source_id} 引用了不存在的材料：{ref}")
        else:
            path = (project / "brief/provided" / item["path"]).resolve()
            if not path.is_relative_to(project) or not path.is_file():
                errors.append(f"source {source_id} 的材料文件不存在")
            elif _digest_file(path) != item.get("sha256"):
                errors.append(f"source {source_id} 的材料哈希不一致")
            else:
                digest = item["sha256"]
                title = Path(item["path"]).name
                locator = item["path"]
    elif kind == "reference":
        index = load_json(project / "references/index.json", {}) or {}
        entry = next(
            (
                value for value in index.get("references", [])
                if isinstance(value, dict) and value.get("id") == ref
            ),
            None,
        )
        if not entry:
            errors.append(f"source {source_id} 引用了不存在的跨区引用：{ref}")
        else:
            path = (project / "references" / entry["path"]).resolve()
            if not path.is_relative_to(project) or not path.is_file():
                errors.append(f"source {source_id} 的引用 manifest 不存在")
            else:
                manifest = load_json(path, {}) or {}
                copied = (project / "references" / manifest.get("copied_path", "")).resolve()
                if not copied.is_relative_to(project) or not copied.is_file():
                    errors.append(f"source {source_id} 的引用副本不存在")
                elif _digest_file(copied) != manifest.get("copied_sha256"):
                    errors.append(f"source {source_id} 的引用副本哈希不一致")
                else:
                    digest = manifest["copied_sha256"]
                    title = manifest.get("artifact_id") or ref
                    locator = manifest.get("copied_path", "")
    else:
        ledger = load_json(project / "synthesis/ledger.json", {}) or {}
        if kind == "design_artifact":
            record = next(
                (
                    item for item in ledger.get("records", [])
                    if item.get("type") == "design_artifact" and item.get("id") == ref
                ),
                None,
            )
            if not record:
                errors.append(f"source {source_id} 引用了不存在的 design artifact：{ref}")
            else:
                title = record.get("title") or ref
                if record.get("path"):
                    path = (project / record["path"]).resolve()
                    if not path.is_relative_to(project) or not path.is_file():
                        errors.append(f"source {source_id} 的设计产物文件不存在")
                    elif _digest_file(path) != record.get("sha256"):
                        errors.append(f"source {source_id} 的设计产物哈希不一致")
                    else:
                        digest = record["sha256"]
                        locator = record["path"]
                else:
                    digest = _digest_json(record)
        elif kind == "alignment":
            record = next(
                (
                    item for item in ledger.get("records", [])
                    if item.get("type") == "alignment" and item.get("round") == ref
                ),
                None,
            )
            if not record:
                errors.append(f"source {source_id} 引用了不存在的 alignment round：{ref}")
            else:
                digest = _digest_json(record)
                title = f"{ref} alignment"
    if expected is not None and digest is not None and expected != digest:
        errors.append(f"source {source_id}.sha256 与当前来源不一致")
    if errors:
        return None, errors
    return {
        "id": source_id,
        "kind": kind,
        "ref": ref,
        "sha256": digest,
        "title": title,
        "locator": locator,
    }, []


def resolve_report_sources(project: Path | str, plan: dict) -> list[dict]:
    project = Path(project).resolve()
    resolved: list[dict] = []
    errors: list[str] = []
    for source in plan.get("sources", []):
        if not isinstance(source, dict):
            errors.append("sources 每项必须是对象")
            continue
        item, source_errors = _resolve_source(project, source)
        errors.extend(source_errors)
        if item:
            resolved.append(item)
    if errors:
        raise ProjectError("\n".join(errors))
    return resolved


def validate_report_plan(project: Path | str, plan: dict) -> list[str]:
    project = Path(project).resolve()
    meta = _require_synthesis(project)
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["ReportPlan 必须是对象"]
    if plan.get("schema") != REPORT_PLAN_SCHEMA:
        errors.append(f"ReportPlan schema 必须是 {REPORT_PLAN_SCHEMA}")
    report_id = plan.get("id")
    if not isinstance(report_id, str) or not REPORT_ID_RE.fullmatch(report_id):
        errors.append("ReportPlan.id 必须是 rpt-NNNN")
    if plan.get("project") != meta.get("id"):
        errors.append("ReportPlan.project 与工作区不一致")
    for field in ("title", "as_of"):
        if not isinstance(plan.get(field), str) or not plan[field].strip():
            errors.append(f"ReportPlan.{field} 必须是非空文本")
    try:
        date.fromisoformat(plan.get("as_of", ""))
    except ValueError:
        errors.append("ReportPlan.as_of 必须是 ISO 日期")
    formats = plan.get("formats")
    if not isinstance(formats, list) or not formats or any(
        value not in REPORT_FORMATS for value in formats
    ):
        errors.append("ReportPlan.formats 必须是 docx、html、pptx 的非空子集")
    elif len(formats) != len(set(formats)):
        errors.append("ReportPlan.formats 不得重复")
    if not isinstance(plan.get("brief", {}), dict):
        errors.append("ReportPlan.brief 必须是对象")
    sources = plan.get("sources")
    if not isinstance(sources, list):
        errors.append("ReportPlan.sources 必须是数组")
        sources = []
    source_ids: set[str] = set()
    for index, source in enumerate(sources):
        mark = f"sources[{index}]"
        if not isinstance(source, dict):
            errors.append(mark + " 必须是对象")
            continue
        source_id = source.get("id")
        if (
            not isinstance(source_id, str)
            or not SOURCE_ID_RE.fullmatch(source_id)
            or source_id in source_ids
        ):
            errors.append(mark + ".id 非法或重复")
        else:
            source_ids.add(source_id)
        if source.get("kind") not in SOURCE_KINDS:
            errors.append(mark + ".kind 非法")
        if not isinstance(source.get("ref"), str) or not source["ref"].strip():
            errors.append(mark + ".ref 必须是非空文本")
        expected = source.get("sha256")
        if expected is not None and (
            not isinstance(expected, str) or not SHA256_RE.fullmatch(expected)
        ):
            errors.append(mark + ".sha256 非法")
    narrative = plan.get("narrative")
    if not isinstance(narrative, dict):
        errors.append("ReportPlan.narrative 必须是对象")
        narrative = {}
    for field in ("core_question", "central_message"):
        if narrative.get(field) is not None and not isinstance(narrative[field], str):
            errors.append(f"narrative.{field} 必须是文本")
    _text_list(narrative.get("angles", []), "angles", errors, "narrative")
    sections = narrative.get("sections")
    if not isinstance(sections, list) or not sections:
        errors.append("narrative.sections 必须是非空数组")
        sections = []
    section_ids: set[str] = set()
    for index, section in enumerate(sections):
        mark = f"narrative.sections[{index}]"
        if not isinstance(section, dict):
            errors.append(mark + " 必须是对象")
            continue
        section_id = section.get("id")
        if (
            not isinstance(section_id, str)
            or not SECTION_ID_RE.fullmatch(section_id)
            or section_id in section_ids
        ):
            errors.append(mark + ".id 非法或重复")
        else:
            section_ids.add(section_id)
        if not isinstance(section.get("title"), str) or not section["title"].strip():
            errors.append(mark + ".title 必须是非空文本")
        level = section.get("level", 1)
        if level not in {1, 2, 3, 4}:
            errors.append(mark + ".level 必须是 1-4")
        _validate_blocks(
            project,
            section.get("blocks"),
            source_ids | set((plan.get("footnotes") or {}).keys()),
            errors,
            mark,
        )
        for field in ("purpose", "release_level", "detail_level"):
            if section.get(field) is not None and not isinstance(section[field], str):
                errors.append(mark + f".{field} 必须是文本")
    content_map = plan.get("content_map")
    if not isinstance(content_map, list):
        errors.append("ReportPlan.content_map 必须是数组")
        content_map = []
    map_ids: set[str] = set()
    for index, item in enumerate(content_map):
        mark = f"content_map[{index}]"
        if not isinstance(item, dict):
            errors.append(mark + " 必须是对象")
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str) or item_id in map_ids:
            errors.append(mark + ".id 缺失或重复")
        else:
            map_ids.add(item_id)
        source_ref = item.get("source_ref")
        if source_ref not in source_ids:
            errors.append(mark + ".source_ref 必须引用 ReportPlan.sources")
        disposition = item.get("disposition")
        if disposition not in DISPOSITIONS:
            errors.append(mark + ".disposition 非法")
        targets = item.get("target_sections", [])
        if not isinstance(targets, list) or any(
            not isinstance(value, str) or not value.strip() for value in targets
        ):
            errors.append(mark + ".target_sections 必须是文本数组")
        else:
            for target in targets:
                if target not in section_ids:
                    errors.append(mark + f".target_sections 引用了不存在的章节：{target}")
            if disposition in {"include", "compress", "redact"} and not targets:
                errors.append(mark + ".target_sections 在采用时不可为空")
        if disposition in {"omit", "redact", "defer"} and not (
            isinstance(item.get("rationale"), str) and item["rationale"].strip()
        ):
            errors.append(mark + ".rationale 在 omit/redact/defer 时不可为空")
    footnotes = plan.get("footnotes", {})
    if not isinstance(footnotes, dict) or any(
        not isinstance(key, str)
        or not SOURCE_ID_RE.fullmatch(key)
        or not isinstance(value, str)
        or not value.strip()
        for key, value in footnotes.items()
    ):
        errors.append("ReportPlan.footnotes 必须是 source-id 到非空文本的对象")
    for field in ("assumptions", "open_issues"):
        _text_list(plan.get(field, []), field, errors, "ReportPlan")
    if not errors:
        try:
            resolve_report_sources(project, plan)
        except ProjectError as exc:
            errors.extend(str(exc).splitlines())
    return errors


def _prefixed_block_text(block: dict) -> str:
    kind = block.get("type")
    if kind == "list":
        return "\n".join(f"• {item}" for item in block.get("items", []))
    if kind == "table":
        return "\n".join(
            " | ".join(row) for row in [block.get("columns", []), *block.get("rows", [])]
        )
    if kind == "figure":
        return f"图：{block.get('caption', '')}"
    if kind == "heading":
        return f"{block.get('text', '')}"
    return block.get("text", "")


def build_report_document(project: Path | str, report_id: str) -> Path:
    project = Path(project).resolve()
    plan = load_report_plan(project, report_id)
    errors = validate_report_plan(project, plan)
    if errors:
        raise ProjectError("\n".join(errors))
    sources = resolve_report_sources(project, plan)
    doc = {
        "schema": DOCUMENT_SCHEMA,
        "project": plan["project"],
        "title": plan["title"],
        "version": plan.get("version", "v0.1"),
        "as_of": plan["as_of"],
        "meta": [
            f"{key}: {value}"
            for key, value in plan.get("brief", {}).items()
        ],
        "sections": [
            {
                "id": section["id"],
                "title": section["title"],
                "level": section.get("level", 1),
                "blocks": copy.deepcopy(section["blocks"]),
                **{
                    key: section[key]
                    for key in ("purpose", "release_level", "detail_level")
                    if key in section
                },
            }
            for section in plan["narrative"]["sections"]
        ],
        "footnotes": copy.deepcopy(plan.get("footnotes", {})),
        "sources": [
            {
                "id": source["id"],
                "title": source["title"],
                "publisher": "Study Arca",
                "grade": source["kind"],
                "locator": source["locator"],
                "retrieved_at": plan["as_of"],
                "source_type": source["kind"],
                "tool": "report",
            }
            for source in sources
        ],
        "generated_from": f"report/{report_id}/plan.json",
        "layer_source": "explicit",
        "report_plan": f"report/{report_id}/plan.json",
        "report_plan_sha256": _digest_file(plan_path(project, report_id)),
        "source_digests": sources,
        "content_map": copy.deepcopy(plan.get("content_map", [])),
    }
    path = document_path(project, report_id)
    _write_json(path, doc)
    _upsert_artifact(
        project,
        report_id,
        artifact_id=f"{report_id}-plan",
        kind="report-plan",
        path=plan_path(project, report_id),
    )
    _upsert_artifact(
        project,
        report_id,
        artifact_id=f"{report_id}-document",
        kind="report-document",
        path=path,
    )
    _update_manifest_sources(project, report_id, sources)
    return path


def validate_report(project: Path | str, report_id: str) -> list[str]:
    project = Path(project).resolve()
    plan = load_report_plan(project, report_id)
    errors = validate_report_plan(project, plan)
    try:
        manifest = _load_manifest(project, report_id)
    except ProjectError as exc:
        errors.append(str(exc))
        return errors
    artifact_ids: set[str] = set()
    for index, artifact in enumerate(manifest.get("artifacts", [])):
        mark = f"manifest.artifacts[{index}]"
        if not isinstance(artifact, dict):
            errors.append(mark + " 必须是对象")
            continue
        artifact_id = artifact.get("id")
        if not isinstance(artifact_id, str) or artifact_id in artifact_ids:
            errors.append(mark + ".id 非法或重复")
        else:
            artifact_ids.add(artifact_id)
        path = project / str(artifact.get("path", ""))
        if not path.resolve().is_relative_to(project) or not path.is_file():
            errors.append(mark + ".path 不存在或越出工作区")
        elif artifact.get("sha256") != _digest_file(path):
            errors.append(mark + ".sha256 不一致")
    doc_path = document_path(project, report_id)
    if doc_path.is_file():
        doc = json.loads(doc_path.read_text(encoding="utf-8-sig"))
        if doc.get("report_plan_sha256") != _digest_file(plan_path(project, report_id)):
            errors.append("ReportDocument 已过期：plan.json 在生成后发生变化")
        for plan_file in sorted((report_dir(project, report_id) / "plans").glob("*.json")):
            if plan_file.stem in {"docx", "html"}:
                value = json.loads(plan_file.read_text(encoding="utf-8-sig"))
                if value.get("source", {}).get("sha256") != _digest_file(doc_path):
                    errors.append(f"格式计划已过期：{plan_file.name}")
    return errors


def report_status(project: Path | str) -> dict:
    project = Path(project).resolve()
    _require_synthesis(project)
    reports = []
    root = _report_root(project)
    for plan_file in sorted(root.glob("rpt-*/plan.json")):
        report_id = plan_file.parent.name
        try:
            plan = load_report_plan(project, report_id)
            errors = validate_report(project, report_id)
        except ProjectError as exc:
            plan = {}
            errors = [str(exc)]
        reports.append({
            "id": report_id,
            "title": plan.get("title"),
            "formats": plan.get("formats", []),
            "status": "ready" if not errors else "invalid",
            "errors": errors,
        })
    return {
        "schema": REPORT_PLAN_SCHEMA,
        "project": _workspace_meta(project).get("id"),
        "reports": reports,
    }


def _format_artifact_ids(report_id: str, output_format: str) -> tuple[str, str | None]:
    plan_id = f"{report_id}-{output_format}-plan"
    layout_id = f"{report_id}-{output_format}-layout" if output_format == "pptx" else None
    return plan_id, layout_id


def _build_docx_or_html(
    project: Path,
    report_id: str,
    plan: dict,
    document_file: Path,
    output_format: str,
) -> dict[str, Path]:
    from .report_outputs import build_report, convert_legacy_report

    plan_id, _ = _format_artifact_ids(report_id, output_format)
    format_plan = convert_legacy_report(
        project,
        document_file,
        snapshot=report_id,
        plan_id=plan_id,
        output_format=output_format,
        title=plan["title"],
    )
    format_plan["report"] = report_id
    format_plan["source_snapshots"] = [
        source["ref"]
        for source in plan.get("sources", [])
        if source.get("kind") == "snapshot"
    ]
    plan_file = report_dir(project, report_id) / "plans" / f"{output_format}.json"
    _write_json(plan_file, format_plan)
    _upsert_artifact(
        project,
        report_id,
        artifact_id=plan_id,
        kind=f"{output_format}-plan",
        path=plan_file,
        format_name=output_format,
    )
    suffix = ".docx" if output_format == "docx" else ".html"
    artifact_file = report_dir(project, report_id) / "artifacts" / f"report{suffix}"
    artifact_file.parent.mkdir(parents=True, exist_ok=True)
    built = build_report(project, format_plan, artifact_file)
    _upsert_artifact(
        project,
        report_id,
        artifact_id=f"{report_id}-{output_format}",
        kind="output",
        path=built,
        format_name=output_format,
    )
    return {"plan": plan_file, "artifact": built}


def _block_text(block: dict) -> str:
    kind = block.get("type")
    if kind == "list":
        return "\n".join(f"• {item}" for item in block.get("items", []))
    if kind == "table":
        rows = [block.get("columns", []), *block.get("rows", [])]
        return "\n".join(" | ".join(str(cell) for cell in row) for row in rows)
    if kind == "figure":
        return f"图：{block.get('caption', '')}".strip()
    if kind == "heading":
        return str(block.get("text", ""))
    return str(block.get("text", ""))


def _section_chunks(section: dict, limit: int = 1400) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for block in section.get("blocks", []):
        text = _block_text(block).strip()
        if not text:
            continue
        if current and size + len(text) + 2 > limit:
            chunks.append("\n\n".join(current))
            current = []
            size = 0
        current.append(text)
        size += len(text) + 2
    if current:
        chunks.append("\n\n".join(current))
    return chunks or [""]


def _deck_from_document(report_id: str, document: dict, document_file: Path, project: Path) -> tuple[dict, dict]:
    texts: dict[str, str] = {}
    slides: list[dict] = []
    layout_slides: list[dict] = []

    title_slide_id = "slide-0001"
    title_ref = f"{title_slide_id}-title"
    subtitle_ref = f"{title_slide_id}-subtitle"
    texts[title_ref] = document.get("title", "")
    texts[subtitle_ref] = (
        f"{document.get('version', '')}  |  as-of {document.get('as_of', '')}  |  "
        f"{document.get('project', '')}"
    )
    slides.append({
        "id": title_slide_id,
        "title": document.get("title", ""),
        "section": "title",
        "sources": "",
        "layer": "inference",
        "notes": "",
    })
    layout_slides.append({
        "id": title_slide_id,
        "background": "#0F172A",
        "elements": [
            {
                "id": "accent",
                "type": "rect",
                "frame": [90, 180, 12, 260],
                "fill": "#38BDF8",
                "stroke": "none",
            },
            {
                "id": "title",
                "type": "text",
                "frame": [140, 220, 1320, 150],
                "content_ref": title_ref,
                "size": 38,
                "bold": True,
                "color": "#F8FAFC",
            },
            {
                "id": "subtitle",
                "type": "text",
                "frame": [140, 410, 1320, 80],
                "content_ref": subtitle_ref,
                "size": 18,
                "color": "#CBD5E1",
            },
        ],
    })

    slide_number = 2
    for section in document.get("sections", []):
        for chunk_index, body in enumerate(_section_chunks(section)):
            slide_id = f"slide-{slide_number:04d}"
            title_ref = f"{slide_id}-title"
            body_ref = f"{slide_id}-body"
            footer_ref = f"{slide_id}-footer"
            title = section.get("title", "")
            if chunk_index:
                title += "（续）"
            texts[title_ref] = title
            texts[body_ref] = body
            texts[footer_ref] = f"{document.get('project', '')} · {document.get('as_of', '')}"
            slides.append({
                "id": slide_id,
                "title": title,
                "section": section.get("id", ""),
                "sources": "",
                "layer": "inference",
                "notes": section.get("purpose", ""),
            })
            layout_slides.append({
                "id": slide_id,
                "background": "#FFFFFF",
                "elements": [
                    {
                        "id": "accent",
                        "type": "rect",
                        "frame": [70, 64, 8, 64],
                        "fill": "#2F5D8A",
                        "stroke": "none",
                    },
                    {
                        "id": "title",
                        "type": "text",
                        "frame": [100, 58, 1400, 76],
                        "content_ref": title_ref,
                        "size": 28,
                        "bold": True,
                        "color": "#1F2937",
                    },
                    {
                        "id": "body",
                        "type": "text",
                        "frame": [100, 170, 1400, 620],
                        "content_ref": body_ref,
                        "size": 18,
                        "color": "#1F2937",
                    },
                    {
                        "id": "footer",
                        "type": "text",
                        "frame": [100, 830, 1400, 32],
                        "content_ref": footer_ref,
                        "size": 10,
                        "color": "#6B7280",
                    },
                ],
            })
            slide_number += 1

    plan_id, layout_id = _format_artifact_ids(report_id, "pptx")
    deck_plan = {
        "schema": "sa.deck-plan/1",
        "artifact_id": plan_id,
        "format": "pptx",
        "snapshot": report_id,
        "report": report_id,
        "title": document.get("title", ""),
        "theme": {"font": "Microsoft YaHei"},
        "texts": texts,
        "slides": slides,
        "source": {
            "content_schema": DOCUMENT_SCHEMA,
            "content_path": _artifact_relative(project, document_file),
            "sha256": _digest_file(document_file),
        },
    }
    render_layout = {
        "schema": "sa.render-layout/1",
        "plan": plan_id,
        "canvas": [1600, 900],
        "coordinate_system": "local-to-parent / px96",
        "slides": layout_slides,
    }
    return deck_plan, render_layout


def _build_pptx(project: Path, report_id: str, plan: dict, document_file: Path) -> dict[str, Path]:
    from .deck import build_pptx, validate_deck

    document = json.loads(document_file.read_text(encoding="utf-8-sig"))
    deck_plan, render_layout = _deck_from_document(
        report_id,
        document,
        document_file,
        project,
    )
    errors = validate_deck(deck_plan, render_layout)
    if errors:
        raise ProjectError("\n".join(errors))
    plan_file = report_dir(project, report_id) / "plans" / "pptx.json"
    layout_file = report_dir(project, report_id) / "plans" / "pptx-layout.json"
    _write_json(plan_file, deck_plan)
    _write_json(layout_file, render_layout)
    plan_id, layout_id = _format_artifact_ids(report_id, "pptx")
    _upsert_artifact(
        project,
        report_id,
        artifact_id=plan_id,
        kind="pptx-plan",
        path=plan_file,
        format_name="pptx",
    )
    _upsert_artifact(
        project,
        report_id,
        artifact_id=layout_id,
        kind="pptx-layout",
        path=layout_file,
        format_name="pptx",
    )
    artifact_file = report_dir(project, report_id) / "artifacts" / "report.pptx"
    artifact_file.parent.mkdir(parents=True, exist_ok=True)
    built = build_pptx(project, deck_plan, render_layout, artifact_file)
    _upsert_artifact(
        project,
        report_id,
        artifact_id=f"{report_id}-pptx",
        kind="output",
        path=built,
        format_name="pptx",
    )
    return {
        "plan": plan_file,
        "layout": layout_file,
        "artifact": built,
    }


def build_report_output(
    project: Path | str,
    report_id: str,
    output_format: str,
) -> dict[str, Path]:
    project = Path(project).resolve()
    if output_format not in REPORT_FORMATS:
        raise ProjectError("report format 必须是 docx、html 或 pptx")
    plan = load_report_plan(project, report_id)
    errors = validate_report_plan(project, plan)
    if errors:
        raise ProjectError("\n".join(errors))
    if output_format not in plan.get("formats", []):
        raise ProjectError(f"ReportPlan 未声明输出格式：{output_format}")
    with _writer(project):
        document_file = build_report_document(project, report_id)
        if output_format in {"docx", "html"}:
            return _build_docx_or_html(
                project,
                report_id,
                plan,
                document_file,
                output_format,
            )
        return _build_pptx(project, report_id, plan, document_file)


def register_report_output(
    project: Path | str,
    report_id: str,
    output_format: str,
    *,
    preview: Path | str | None = None,
) -> str:
    from .output_registry import apply_records, init_registry, load_registry

    project = Path(project).resolve()
    if output_format not in REPORT_FORMATS:
        raise ProjectError("report format 必须是 docx、html 或 pptx")
    errors = validate_report(project, report_id)
    if errors:
        raise ProjectError("\n".join(errors))
    plan_id, layout_id = _format_artifact_ids(report_id, output_format)
    artifact_id = f"{report_id}-{output_format}"
    manifest = _load_manifest(project, report_id)
    indexed = {item["id"]: item for item in manifest.get("artifacts", [])}
    for needed in [f"{report_id}-plan", f"{report_id}-document", plan_id, artifact_id]:
        if needed not in indexed:
            raise ProjectError(f"报告 artifact 尚未生成：{needed}")
    if output_format == "pptx" and layout_id not in indexed:
        raise ProjectError(f"报告 artifact 尚未生成：{layout_id}")

    preview_id = None
    if preview is not None:
        source = Path(preview)
        if not source.is_absolute():
            source = project / source
        source = source.resolve()
        if not source.is_file() or not source.is_relative_to(project):
            raise ProjectError("report preview 必须是工作区内文件")
        destination = report_dir(project, report_id) / "previews" / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.resolve() != source:
            destination.write_bytes(source.read_bytes())
        preview_id = f"{report_id}-{output_format}-preview"
        _upsert_artifact(
            project,
            report_id,
            artifact_id=preview_id,
            kind="preview",
            path=destination,
            format_name=output_format,
        )

    output_id = f"o-{report_id}-{output_format}"
    try:
        load_registry(project)
    except ProjectError:
        init_registry(project)
    record = {
        "id": output_id,
        "type": "output",
        "format": output_format,
        "report": report_id,
        "request": f"{report_id}-plan",
        "plan": plan_id,
        "artifact": artifact_id,
        "preview": preview_id,
        "renderer": "study-arca-report",
        "source_snapshots": [
            source["ref"]
            for source in manifest.get("sources", [])
            if source.get("kind") == "snapshot"
        ],
    }
    if layout_id:
        record["layout"] = layout_id
    apply_records(project, record)
    return output_id


def report_artifact_index(project: Path | str) -> dict[str, dict]:
    project = Path(project).resolve()
    index: dict[str, dict] = {}
    for manifest_file in sorted(_report_root(project).glob("rpt-*/manifest.json")):
        report_id = manifest_file.parent.name
        manifest = _load_manifest(project, report_id)
        for artifact in manifest.get("artifacts", []):
            if not isinstance(artifact, dict) or not artifact.get("id"):
                continue
            artifact_id = artifact["id"]
            if artifact_id in index:
                raise ProjectError(f"报告 artifact ID 重复：{artifact_id}")
            if not isinstance(artifact.get("path"), str) or not isinstance(
                artifact.get("sha256"), str
            ):
                raise ProjectError(f"报告 artifact 字段不完整：{artifact_id}")
            path = (project / artifact["path"]).resolve()
            if not path.is_relative_to(project) or not path.is_file():
                raise ProjectError(f"报告 artifact 文件不存在或越出工作区：{artifact_id}")
            if _digest_file(path) != artifact["sha256"]:
                raise ProjectError(f"报告 artifact 哈希不一致：{artifact_id}")
            index[artifact_id] = {
                **artifact,
                "report": report_id,
            }
    return index
