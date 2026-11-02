"""DocumentPlan and ExperiencePlan projections for DOCX and HTML outputs."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

from .project import ProjectError

DOCUMENT_SCHEMA = "sa.document/1"
DOCUMENT_PLAN_SCHEMA = "sa.document-plan/1"
EXPERIENCE_PLAN_SCHEMA = "sa.experience-plan/1"
PLAN_FORMATS = {
    "docx": (DOCUMENT_PLAN_SCHEMA, "sa.document-plan/1"),
    "html": (EXPERIENCE_PLAN_SCHEMA, "sa.experience-plan/1"),
}
SECTION_LEVELS = {1, 2, 3, 4}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_document(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ProjectError(f"无法读取报告源 {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProjectError(f"报告源必须是 JSON 对象：{path}")
    if value.get("schema") != DOCUMENT_SCHEMA:
        raise ProjectError(f"报告源 schema 必须是 {DOCUMENT_SCHEMA}")
    return value


def _local_path(project: Path, value: Path | str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = project / path
    path = path.resolve()
    if not path.is_relative_to(project):
        raise ProjectError("报告输出文件必须位于项目目录")
    return path


def _validate_sections(plan: dict, errors: list[str]) -> None:
    sections = plan.get("sections")
    if not isinstance(sections, list):
        errors.append("plan.sections 必须是数组")
        return
    seen = set()
    for index, section in enumerate(sections):
        mark = f"sections[{index}]"
        if not isinstance(section, dict):
            errors.append(f"{mark} 必须是对象")
            continue
        section_id = section.get("id")
        if not isinstance(section_id, str) or not section_id.strip() or section_id in seen:
            errors.append(f"{mark}.id 缺失或重复")
        else:
            seen.add(section_id)
        if not isinstance(section.get("title"), str):
            errors.append(f"{mark}.title 必须是文本")
        if section.get("level") not in SECTION_LEVELS:
            errors.append(f"{mark}.level 必须是 1-4")
        if not isinstance(section.get("blocks"), list):
            errors.append(f"{mark}.blocks 必须是数组")


def validate_report_plan(plan: dict, expected_format: str | None = None) -> list[str]:
    errors: list[str] = []
    output_format = plan.get("format")
    if output_format not in PLAN_FORMATS:
        return ["plan.format 必须是 docx 或 html"]
    if expected_format is not None and output_format != expected_format:
        errors.append(f"plan.format 必须是 {expected_format}")
    expected_schema = PLAN_FORMATS[output_format][0]
    if plan.get("schema") != expected_schema:
        errors.append(f"plan.schema 必须是 {expected_schema}")
    if not isinstance(plan.get("artifact_id"), str) or not plan["artifact_id"].strip():
        errors.append("plan.artifact_id 必须是非空 artifact ID")
    if not isinstance(plan.get("snapshot"), str) or not plan["snapshot"].strip():
        errors.append("plan.snapshot 必须是非空 artifact ID")
    if not isinstance(plan.get("title"), str) or not plan["title"].strip():
        errors.append("plan.title 必须是非空文本")
    if not isinstance(plan.get("meta"), list):
        errors.append("plan.meta 必须是数组")
    if not isinstance(plan.get("footnotes"), dict):
        errors.append("plan.footnotes 必须是对象")
    sources = plan.get("sources")
    if not isinstance(sources, list):
        errors.append("plan.sources 必须是数组")
    else:
        source_ids = [item.get("id") for item in sources if isinstance(item, dict)]
        if len(source_ids) != len(sources) or any(not isinstance(item, str) or not item for item in source_ids):
            errors.append("plan.sources 每项必须有非空 id")
        elif len(source_ids) != len(set(source_ids)):
            errors.append("plan.sources id 重复")
    _validate_sections(plan, errors)
    source = plan.get("source")
    if not isinstance(source, dict):
        errors.append("plan.source 必须是对象")
    else:
        for field in ("schema", "path", "sha256"):
            if not isinstance(source.get(field), str) or not source[field].strip():
                errors.append(f"plan.source.{field} 必须是非空文本")
    if output_format == "html":
        navigation = plan.get("navigation")
        if not isinstance(navigation, list):
            errors.append("experience plan.navigation 必须是数组")
        else:
            section_ids = {
                section.get("id")
                for section in plan.get("sections", [])
                if isinstance(section, dict)
            }
            for index, item in enumerate(navigation):
                if not isinstance(item, dict) or item.get("id") not in section_ids:
                    errors.append(f"plan.navigation[{index}] 必须引用现有 section")
        controls = plan.get("controls")
        if not isinstance(controls, dict):
            errors.append("experience plan.controls 必须是对象")
    return errors


def convert_legacy_report(
    project: Path | str,
    source: Path | str,
    *,
    snapshot: str,
    plan_id: str,
    output_format: str,
    title: str | None = None,
) -> dict:
    if output_format not in PLAN_FORMATS:
        raise ProjectError("output_format 必须是 docx 或 html")
    project = Path(project).resolve()
    source_path = _local_path(project, source)
    if not source_path.is_file():
        raise ProjectError(f"报告源不存在：{source_path}")
    document = _read_document(source_path)
    relative = source_path.relative_to(project).as_posix()
    plan = {
        "schema": PLAN_FORMATS[output_format][0],
        "artifact_id": plan_id,
        "format": output_format,
        "snapshot": snapshot,
        "title": title or document.get("title") or project.name,
        "version": document.get("version", ""),
        "as_of": document.get("as_of", ""),
        "project": document.get("project", ""),
        "meta": copy.deepcopy(document.get("meta", [])),
        "sections": copy.deepcopy(document.get("sections", [])),
        "footnotes": copy.deepcopy(document.get("footnotes", {})),
        "sources": copy.deepcopy(document.get("sources", [])),
        "generated_from": document.get("generated_from", ""),
        "layer_source": document.get("layer_source", ""),
        "source": {
            "schema": document.get("schema"),
            "path": relative,
            "sha256": _sha256(source_path),
        },
    }
    if output_format == "html":
        plan["navigation"] = [
            {"id": section.get("id"), "title": section.get("title"), "level": section.get("level")}
            for section in plan["sections"]
            if isinstance(section, dict)
        ]
        plan["controls"] = {
            "search": True,
            "layer_filters": ["all", "fact", "inference", "option"],
            "citation_drawer": True,
            "print": True,
        }
    errors = validate_report_plan(plan, output_format)
    if errors:
        raise ProjectError("\n".join(errors))
    return plan


def _render_view(plan: dict) -> dict:
    view = copy.deepcopy(plan)
    view["schema"] = plan.get("source", {}).get("schema", DOCUMENT_SCHEMA)
    return view


def build_report(project: Path | str, plan: dict, output: Path | str) -> Path:
    output_format = plan.get("format")
    errors = validate_report_plan(plan, output_format)
    if errors:
        raise ProjectError("\n".join(errors))
    project = Path(project).resolve()
    output_path = _local_path(project, output)
    document = _render_view(plan)
    if output_format == "docx":
        from .docx_render import render_docx

        return render_docx(project, document, output=output_path)
    from .render import render_html

    return render_html(project, document, output=output_path)


def inspect_report_output(path: Path | str) -> dict:
    path = Path(path).resolve()
    if not path.is_file():
        raise ProjectError(f"报告产物不存在：{path}")
    suffix = path.suffix.lower()
    if suffix == ".html":
        text = path.read_text(encoding="utf-8")
        section_ids = []
        for tag in re.findall(
            r"<section\b[^>]*\bclass=[\"'][^\"']*\bdoc-section\b[^\"']*[\"'][^>]*>",
            text,
            flags=re.IGNORECASE,
        ):
            match = re.search(r"\bid=[\"']([^\"']+)[\"']", tag, flags=re.IGNORECASE)
            if match:
                section_ids.append(match.group(1))
        external_assets = re.findall(
            r"<(?:script|img)\b[^>]*\bsrc=[\"'](https?://[^\"']+)",
            text,
            flags=re.IGNORECASE,
        )
        external_assets += re.findall(
            r"<link\b[^>]*\bhref=[\"'](https?://[^\"']+)",
            text,
            flags=re.IGNORECASE,
        )
        return {
            "format": "html",
            "bytes": path.stat().st_size,
            "sections": sum(section_id != "refs" for section_id in section_ids),
            "reference_sections": sum(section_id == "refs" for section_id in section_ids),
            "citations": len(re.findall(r'class="cite\b', text)),
            "external_assets": external_assets,
            "self_contained": not external_assets,
        }
    if suffix == ".docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise ProjectError("缺少 python-docx，无法检查 DOCX") from exc
        document = Document(path)
        return {
            "format": "docx",
            "bytes": path.stat().st_size,
            "paragraphs": len(document.paragraphs),
            "tables": len(document.tables),
            "sections": len(document.sections),
        }
    raise ProjectError(f"不支持的报告产物：{path.suffix}")
