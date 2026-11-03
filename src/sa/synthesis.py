"""Minimal scaffolding for synthesis workspaces."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from .project import ProjectError, load_json, save_json


SCHEMA = "sa.synthesis/1"
WORK_MODEL_SCHEMA = "sa.work-model/1"
ITEM_STATUS = {"planned", "active", "blocked", "done", "unknown"}
CONTENT_LAYERS = {"user_statement", "material", "inference", "unknown"}
LAYER_LABELS = {
    "user_statement": "用户陈述",
    "material": "材料记录",
    "inference": "代理归纳",
    "unknown": "未知",
}


def ledger_path(project: Path | str) -> Path:
    return Path(project) / "synthesis/ledger.json"


def model_path(project: Path | str) -> Path:
    return Path(project) / "work-model/model.json"


def init_synthesis(project: Path | str) -> Path:
    project = Path(project)
    meta = load_json(project / "project.json", {}) or {}
    if not meta.get("id"):
        raise ProjectError("不是有效工作区")
    path = ledger_path(project)
    if path.exists():
        validate_synthesis(project)
        return path
    save_json(path, {"schema": SCHEMA, "project": meta["id"], "records": []})
    model = model_path(project)
    if not model.exists():
        save_json(model, {
            "schema": WORK_MODEL_SCHEMA,
            "project": meta["id"],
            "as_of": date.today().isoformat(),
            "audience": "",
            "period": {"start": None, "end": None},
            "overview": "",
            "items": [],
            "unknowns": [],
        })
    for rel in ("work-model", "synthesis"):
        keep = project / rel / ".gitkeep"
        if keep.exists():
            keep.unlink()
    (project / "synthesis/README.md").write_text(
        "# 总结记录\n\n"
        "当前机器真相为 `ledger.json`。总结型工作区独立使用 `sa.synthesis/1`，"
        "不从研究循环推断状态。\n",
        encoding="utf-8",
    )
    (project / "work-model/README.md").write_text(
        "# 工作模型\n\n"
        "保存从用户材料归一化得到的工作主题、进展、结果、阻塞、依赖和未知项。"
        "代理归纳必须能回指 `brief/provided/` 中的材料。\n",
        encoding="utf-8",
    )
    return path


def validate_synthesis(project: Path | str) -> list[str]:
    project = Path(project)
    path = ledger_path(project)
    if not path.is_file():
        return ["缺少 synthesis/ledger.json"]
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return [f"synthesis ledger 不是合法 JSON：{exc}"]
    meta = load_json(project / "project.json", {}) or {}
    errors: list[str] = []
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return [f"synthesis ledger schema 必须是 {SCHEMA}"]
    if data.get("project") != meta.get("id"):
        errors.append("synthesis ledger project 与 project.json 不一致")
    if not isinstance(data.get("records"), list):
        errors.append("synthesis ledger records 必须是数组")
    model_file = model_path(project)
    if not model_file.is_file():
        errors.append("缺少 work-model/model.json")
        return errors
    try:
        model = json.loads(model_file.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        errors.append(f"work model 不是合法 JSON：{exc}")
        return errors
    if not isinstance(model, dict) or model.get("schema") != WORK_MODEL_SCHEMA:
        errors.append(f"work model schema 必须是 {WORK_MODEL_SCHEMA}")
        return errors
    if model.get("project") != meta.get("id"):
        errors.append("work model project 与 project.json 不一致")
    try:
        date.fromisoformat(str(model.get("as_of", "")))
    except ValueError:
        errors.append("work model as_of 必须是 ISO 日期")
    if not isinstance(model.get("audience"), str):
        errors.append("work model audience 必须是文本")
    period = model.get("period")
    if not isinstance(period, dict):
        errors.append("work model period 必须是对象")
    if not isinstance(model.get("overview"), str):
        errors.append("work model overview 必须是文本")
    if not isinstance(model.get("unknowns"), list) or any(
        not isinstance(value, str) or not value.strip() for value in model.get("unknowns", [])
    ):
        errors.append("work model unknowns 必须是非空文本数组")
    items = model.get("items")
    if not isinstance(items, list):
        return errors + ["work model items 必须是数组"]
    seen: set[str] = set()
    for index, item in enumerate(items):
        mark = f"work-model.items[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{mark} 必须是对象")
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str) or not re.fullmatch(r"w-\d{4}", item_id) or item_id in seen:
            errors.append(f"{mark}.id 非法或重复")
            continue
        seen.add(item_id)
        if item.get("status") not in ITEM_STATUS:
            errors.append(f"{mark}.status 非法")
        for field in ("title", "goal"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"{mark}.{field} 必须是非空文本")
        provided = load_json(project / "brief/provided/manifest.json", {}) or {}
        references = load_json(project / "references/index.json", {}) or {}
        known_materials = {
            item.get("id") for item in provided.get("items", []) if isinstance(item, dict)
        }
        known_materials.update(
            item.get("id") for item in references.get("references", []) if isinstance(item, dict)
        )
        for material in item.get("materials", []):
            if material not in known_materials:
                errors.append(f"{mark}.materials 引用了不存在的材料：{material}")
        for field in ("progress", "outcomes", "blockers", "next_steps"):
            values = item.get(field)
            if not isinstance(values, list):
                errors.append(f"{mark}.{field} 必须是数组")
                continue
            for entry_index, value in enumerate(values):
                entry_mark = f"{mark}.{field}[{entry_index}]"
                if isinstance(value, str):
                    if not value.strip():
                        errors.append(f"{entry_mark} 不能为空")
                    continue
                if not isinstance(value, dict):
                    errors.append(f"{entry_mark} 必须是文本或 {text/layer/materials} 对象")
                    continue
                if not isinstance(value.get("text"), str) or not value["text"].strip():
                    errors.append(f"{entry_mark}.text 必须是非空文本")
                if value.get("layer") not in CONTENT_LAYERS:
                    errors.append(f"{entry_mark}.layer 非法")
                materials = value.get("materials", [])
                if not isinstance(materials, list) or any(
                    not isinstance(material, str) or not material.strip()
                    for material in materials
                ):
                    errors.append(f"{entry_mark}.materials 必须是文本数组")
                else:
                    for material in materials:
                        if material not in known_materials:
                            errors.append(
                                f"{entry_mark}.materials 引用了不存在的材料：{material}"
                            )
    return errors


def _bullets(values: list[str]) -> str:
    return "\n".join(f"- {value}" for value in values) if values else "- 未提供"


def _content_entries(item: dict, field: str) -> list[dict]:
    defaults = item.get("materials", [])
    entries = []
    for value in item.get(field, []):
        if isinstance(value, str):
            entries.append({
                "text": value,
                "layer": "user_statement",
                "materials": list(defaults),
            })
        else:
            entries.append({
                "text": value["text"],
                "layer": value["layer"],
                "materials": value.get("materials", defaults),
            })
    return entries


def _annotated_bullets(item: dict, field: str) -> str:
    entries = _content_entries(item, field)
    if not entries:
        return "- 未提供"
    lines = []
    for entry in entries:
        materials = "、".join(entry["materials"])
        suffix = f"（材料：{materials}）" if materials else ""
        lines.append(f"- [{LAYER_LABELS[entry['layer']]}] {entry['text']}{suffix}")
    return "\n".join(lines)


def render_summary_markdown(project: Path | str) -> Path:
    project = Path(project)
    errors = validate_synthesis(project)
    if errors:
        raise ProjectError("\n".join(errors))
    meta = load_json(project / "project.json", {}) or {}
    model = load_json(model_path(project), {}) or {}
    lines = [
        f"# {meta.get('title') or '工作情况汇总'}",
        "",
        f"as-of：{model['as_of']}",
        "",
    ]
    period = model.get("period", {})
    if period.get("start") or period.get("end"):
        lines.append(f"覆盖期间：{period.get('start') or '未知'} 至 {period.get('end') or '未知'}")
        lines.append("")
    if model.get("audience"):
        lines.append(f"读者：{model['audience']}")
        lines.append("")
    lines.extend(["## 概览", "", model.get("overview") or "用户未提供概览。", ""])
    items = model.get("items", [])
    if items:
        lines.extend([
            "## 工作主题总表",
            "",
            "| 主题 | 状态 | 目标 | 材料 |",
            "|---|---|---|---|",
        ])
        for item in items:
            materials = "、".join(item.get("materials", [])) or "未提供"
            lines.append(
                f"| {item['title']} | {item['status']} | {item['goal']} | {materials} |"
            )
        lines.append("")
        lines.append("## 分主题进展")
        lines.append("")
        for item in items:
            lines.extend([
                f"### {item['title']}",
                "",
                f"目标：{item['goal']}",
                "",
                "进展：",
                _annotated_bullets(item, "progress"),
                "",
                "结果：",
                _annotated_bullets(item, "outcomes"),
                "",
                "阻塞与依赖：",
                _annotated_bullets(item, "blockers"),
                "",
                "已计划事项：",
                _annotated_bullets(item, "next_steps"),
                "",
            ])
    else:
        lines.extend(["## 工作主题", "", "用户尚未提供可归纳的工作主题。", ""])
    lines.extend(["## 未知与待确认", "", _bullets(model.get("unknowns", [])), ""])
    output = project / "report/work-summary.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def build_synthesis_document(project: Path | str, model: dict | None = None) -> dict:
    project = Path(project)
    errors = validate_synthesis(project)
    if errors:
        raise ProjectError("\n".join(errors))
    meta = load_json(project / "project.json", {}) or {}
    model = model or load_json(model_path(project), {}) or {}
    sections: list[dict] = []

    def section(section_id: str, title: str, blocks: list[dict], level: int = 1) -> None:
        sections.append({
            "id": section_id,
            "title": title,
            "level": level,
            "blocks": blocks,
        })

    overview = model.get("overview") or "用户未提供概览。"
    section("overview", "概览", [{
        "type": "paragraph",
        "layer": "inference",
        "text": overview,
    }])

    items = model.get("items", [])
    rows = [
        [
            item["title"],
            item["status"],
            item["goal"],
            "、".join(item.get("materials", [])) or "未提供",
        ]
        for item in items
    ]
    section("work-items", "工作主题总表", [{
        "type": "table",
        "layer": "inference",
        "columns": ["主题", "状态", "目标", "材料"],
        "rows": rows,
    }])

    item_sections = []
    for item in items:
        blocks: list[dict] = [{
            "type": "paragraph",
            "layer": "inference",
            "text": f"目标：{item['goal']}",
        }]
        for field, label in (
            ("progress", "进展"),
            ("outcomes", "结果"),
            ("blockers", "阻塞与依赖"),
            ("next_steps", "已计划事项"),
        ):
            blocks.append({
                "type": "heading",
                "level": 3,
                "text": label,
            })
            entries = _content_entries(item, field)
            if not entries:
                blocks.append({
                    "type": "paragraph",
                    "layer": "unknown",
                    "text": "未提供",
                })
                continue
            for entry in entries:
                materials = "、".join(entry["materials"])
                text = entry["text"] + (f"（材料：{materials}）" if materials else "")
                blocks.append({
                    "type": "paragraph",
                    "layer": entry["layer"],
                    "text": text,
                })
        item_sections.append({
            "id": f"item-{item['id']}",
            "title": item["title"],
            "level": 2,
            "blocks": blocks,
        })
    section("details", "分主题进展", [] if items else [{
        "type": "paragraph",
        "layer": "unknown",
        "text": "用户尚未提供可归纳的工作主题。",
    }])
    sections.extend(item_sections)

    unknown_blocks = [
        {"type": "paragraph", "layer": "unknown", "text": value}
        for value in model.get("unknowns", [])
    ] or [{"type": "paragraph", "layer": "unknown", "text": "未提供"}]
    section("unknowns", "未知与待确认", unknown_blocks)

    material_ids = sorted({
        material
        for item in items
        for key in ("progress", "outcomes", "blockers", "next_steps")
        for entry in _content_entries(item, key)
        for material in entry["materials"]
    })
    section("materials", "材料索引", [{
        "type": "list",
        "layer": "material",
        "items": material_ids or ["未提供"],
    }])
    return {
        "schema": "sa.document/1",
        "project": meta.get("id"),
        "title": meta.get("title") or "工作情况汇总",
        "version": "v0.1",
        "as_of": model["as_of"],
        "layers": sorted(CONTENT_LAYERS),
        "sections": sections,
        "sources": [],
        "footnotes": {},
        "generated_from": "work-model/model.json",
        "layer_source": "explicit",
    }


def build_synthesis_report(project: Path | str, *, docx: bool = False) -> dict:
    project = Path(project)
    source = render_summary_markdown(project)
    from .render import render_html, write_document

    document = build_synthesis_document(project)
    document_path = write_document(project, document)
    html_path = render_html(project, document)
    outputs = {
        "markdown": source,
        "document": document_path,
        "html": html_path,
    }
    if docx:
        from .docx_render import render_docx
        outputs["docx"] = render_docx(project, document)
    return outputs
