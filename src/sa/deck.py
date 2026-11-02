"""DeckPlan / RenderLayout migration and native PPTX compilation."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from .project import ProjectError

PLAN_SCHEMA = "sa.deck-plan/1"
LAYOUT_SCHEMA = "sa.render-layout/1"
SUPPORTED_TYPES = {"group", "text", "rect", "ellipse", "path", "image", "connector"}


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ProjectError(f"无法读取 JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProjectError(f"JSON 根必须是对象：{path}")
    return value


def convert_legacy_deck(
    project: Path | str,
    content_path: Path | str,
    layout_path: Path | str,
    *,
    snapshot: str,
    plan_id: str,
    title: str | None = None,
) -> tuple[dict, dict]:
    project = Path(project).resolve()
    content_file = (project / content_path).resolve()
    layout_file = (project / layout_path).resolve()
    content = _read_json(content_file)
    layout = _read_json(layout_file)
    texts = dict(content.get("texts", {}) or {})
    content_slides = {
        slide.get("id"): slide
        for slide in content.get("slides", []) or []
        if isinstance(slide, dict) and slide.get("id")
    }
    converted_slides = []
    plan_slides = []

    def convert_nodes(slide_id: str, nodes: list[dict]) -> None:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = node.get("id", "element")
            if node.get("type") == "text":
                reference = node.get("content_ref")
                if reference:
                    content_id = str(reference).split("/")[-1]
                else:
                    content_id = f"{slide_id}--{node_id}"
                    texts[content_id] = (
                        str(node.get("prefix", ""))
                        + str(node.get("text", ""))
                        + str(node.get("suffix", ""))
                    )
                node.pop("text", None)
                node.pop("prefix", None)
                node.pop("suffix", None)
                node["content_ref"] = content_id
            if node.get("type") == "group":
                convert_nodes(slide_id, node.get("children", []) or [])

    for slide in layout.get("slides", []) or []:
        slide_id = slide["id"]
        converted = copy.deepcopy(slide)
        convert_nodes(slide_id, converted.get("elements", []) or [])
        converted_slides.append(converted)
        metadata = content_slides.get(slide_id, {})
        plan_slides.append({
            "id": slide_id,
            "title": metadata.get("title", converted.get("title", "")),
            "section": metadata.get("section", converted.get("section", "")),
            "sources": metadata.get("sources", converted.get("sources", "")),
            "layer": metadata.get("layer", converted.get("layer", "")),
            "notes": metadata.get("notes", converted.get("notes", "")),
        })

    canvas = layout.get("canvas", [1600, 900])
    plan = {
        "schema": PLAN_SCHEMA,
        "artifact_id": plan_id,
        "format": "pptx",
        "snapshot": snapshot,
        "title": title or content.get("title") or project.name,
        "theme": {"font": "Microsoft YaHei"},
        "texts": texts,
        "slides": plan_slides,
        "source": {
            "content_schema": content.get("schema"),
            "layout_schema": layout.get("schema"),
            "content_path": content_file.relative_to(project).as_posix(),
            "layout_path": layout_file.relative_to(project).as_posix(),
        },
    }
    converted_layout = {
        "schema": LAYOUT_SCHEMA,
        "plan": plan_id,
        "canvas": canvas,
        "coordinate_system": layout.get("coordinate_system", "local-to-parent / px96"),
        "slides": converted_slides,
    }
    errors = validate_deck(plan, converted_layout)
    if errors:
        raise ProjectError("\n".join(errors))
    return plan, converted_layout


def _validate_nodes(slide_id: str, nodes: list[dict], texts: dict, errors: list[str]) -> None:
    node_ids = set()
    for node in nodes:
        if not isinstance(node, dict):
            errors.append(f"{slide_id}: 元素必须是对象")
            continue
        node_id = node.get("id")
        kind = node.get("type")
        if not isinstance(node_id, str) or not node_id:
            errors.append(f"{slide_id}: 元素缺少 ID")
            continue
        if node_id in node_ids:
            errors.append(f"{slide_id}: 元素 ID 重复 {node_id}")
        node_ids.add(node_id)
        if kind not in SUPPORTED_TYPES:
            errors.append(f"{slide_id}.{node_id}: 不支持的元素类型 {kind}")
            continue
        if kind != "connector":
            frame = node.get("frame")
            if not isinstance(frame, list) or len(frame) != 4 or not all(isinstance(v, (int, float)) for v in frame):
                errors.append(f"{slide_id}.{node_id}: frame 必须是四个数字")
        if kind == "text" and node.get("content_ref") not in texts:
            errors.append(f"{slide_id}.{node_id}: content_ref 不存在 {node.get('content_ref')}")
        if kind == "path":
            if not isinstance(node.get("viewbox"), list) or len(node["viewbox"]) != 2:
                errors.append(f"{slide_id}.{node_id}: path 缺少 viewbox")
            if not isinstance(node.get("commands"), list) or not node["commands"]:
                errors.append(f"{slide_id}.{node_id}: path 缺少 commands")
        if kind == "group":
            _validate_nodes(slide_id, node.get("children", []) or [], texts, errors)
        if kind == "connector":
            for endpoint in ("from", "to"):
                ref = node.get(endpoint)
                if not isinstance(ref, dict) or not isinstance(ref.get("node"), str):
                    errors.append(f"{slide_id}.{node_id}: {endpoint} 必须包含 node")


def validate_deck(plan: dict, layout: dict) -> list[str]:
    errors: list[str] = []
    if plan.get("schema") != PLAN_SCHEMA:
        errors.append(f"deck plan schema 必须是 {PLAN_SCHEMA}")
    if not isinstance(plan.get("artifact_id"), str) or not plan["artifact_id"].strip():
        errors.append("deck plan artifact_id 必须是非空 artifact ID")
    if plan.get("format") != "pptx":
        errors.append("deck plan format 必须是 pptx")
    texts = plan.get("texts")
    if not isinstance(texts, dict):
        errors.append("deck plan texts 必须是对象")
        texts = {}
    plan_slides = plan.get("slides")
    if not isinstance(plan_slides, list):
        errors.append("deck plan slides 必须是数组")
        plan_slides = []
    plan_ids = [slide.get("id") for slide in plan_slides if isinstance(slide, dict)]
    if len(plan_ids) != len(set(plan_ids)) or any(not isinstance(value, str) or not value for value in plan_ids):
        errors.append("deck plan slide ID 缺失或重复")

    if layout.get("schema") != LAYOUT_SCHEMA:
        errors.append(f"render layout schema 必须是 {LAYOUT_SCHEMA}")
    if not isinstance(layout.get("plan"), str) or not layout["plan"].strip():
        errors.append("render layout plan 必须是 artifact ID")
    elif plan.get("artifact_id") and layout["plan"] != plan["artifact_id"]:
        errors.append("render layout plan 与 deck plan artifact_id 不一致")
    if not isinstance(layout.get("canvas"), list) or len(layout["canvas"]) != 2:
        errors.append("render layout canvas 必须是 [width, height]")
    layout_slides = layout.get("slides")
    if not isinstance(layout_slides, list):
        errors.append("render layout slides 必须是数组")
        layout_slides = []
    layout_ids = [slide.get("id") for slide in layout_slides if isinstance(slide, dict)]
    if layout_ids != plan_ids:
        errors.append("deck plan 与 render layout 的页面 ID/顺序不一致")
    for slide in layout_slides:
        if not isinstance(slide, dict):
            errors.append("render layout slide 必须是对象")
            continue
        slide_id = slide.get("id", "?")
        elements = slide.get("elements", []) or []
        _validate_nodes(str(slide_id), elements, texts, errors)
        all_nodes: dict[str, dict] = {}

        def collect(nodes):
            for node in nodes:
                if isinstance(node, dict) and node.get("id"):
                    all_nodes[node["id"]] = node
                if isinstance(node, dict) and node.get("type") == "group":
                    collect(node.get("children", []) or [])

        collect(elements)
        for node in elements:
            if isinstance(node, dict) and node.get("type") == "connector":
                for endpoint in ("from", "to"):
                    target = (node.get(endpoint) or {}).get("node")
                    if target not in all_nodes:
                        errors.append(f"{slide_id}.{node.get('id')}: {endpoint} 指向不存在元素 {target}")
    return errors


def _xml(tag, **attrs):
    from pptx.oxml.xmlchemy import OxmlElement
    element = OxmlElement(tag)
    for key, value in attrs.items():
        element.set(key, str(value))
    return element


def _paint(shape, element: dict) -> None:
    from pptx.dml.color import RGBColor
    from pptx.util import Pt
    fill = element.get("fill", "none")
    if fill == "none":
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor.from_string(fill.lstrip("#"))
    stroke = element.get("stroke", "none")
    if stroke == "none":
        shape.line.fill.background()
    else:
        shape.line.color.rgb = RGBColor.from_string(stroke.lstrip("#"))
        shape.line.width = Pt(element.get("stroke_width", 1) * 0.75)
    shape._element.spPr.append(_xml("a:effectLst"))
    for ref in shape._element.xpath(".//a:effectRef"):
        ref.set("idx", "0")


def _resolve_connectors(slide: dict) -> list[dict]:
    index: dict[str, tuple[float, float, float, float]] = {}

    def scan(nodes, ox=0, oy=0):
        for node in nodes:
            if node.get("type") == "connector":
                continue
            x, y, width, height = node["frame"]
            index[node["id"]] = (x + ox, y + oy, width, height)
            if node.get("type") == "group":
                scan(node.get("children", []) or [], x + ox, y + oy)

    scan(slide.get("elements", []) or [])
    output = []
    for node in slide.get("elements", []) or []:
        if node.get("type") != "connector":
            output.append(node)
            continue
        points = []
        for endpoint in ("from", "to"):
            ref = node[endpoint]
            x, y, width, height = index[ref["node"]]
            ax, ay = ref.get("anchor", [0.5, 0.5])
            points.append((x + width * ax, y + height * ay))
        first, second = points
        bend_x, bend_y = node.get("bend", [0, 0])
        output.append({
            "id": node["id"],
            "type": "path",
            "frame": [0, 0, *slide.get("canvas", [1600, 900])],
            "viewbox": slide.get("canvas", [1600, 900]),
            "commands": [["M", *first], ["Q", (first[0] + second[0]) / 2 + bend_x, (first[1] + second[1]) / 2 + bend_y, *second]],
            "fill": "none",
            "stroke": node.get("stroke", "#000000"),
            "stroke_width": node.get("stroke_width", 1.5),
        })
    return output


def _add_nodes(shapes, nodes: list[dict], texts: dict, project: Path, font: str, ox=0, oy=0) -> None:
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches, Pt

    def unit(value):
        return Inches(value / 96)

    for element in nodes:
        x, y, width, height = element["frame"]
        x += ox
        y += oy
        kind = element["type"]
        if kind == "group":
            shape = shapes.add_group_shape()
            shape.name = element["id"]
            _add_nodes(shape.shapes, element.get("children", []) or [], texts, project, font, x, y)
            continue
        if kind == "text":
            shape = shapes.add_textbox(unit(x), unit(y), unit(width), unit(height))
            frame = shape.text_frame
            frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
            frame.word_wrap = True
            value = str(texts[element["content_ref"]])
            for index, line in enumerate(value.split("\n")):
                paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
                paragraph.text = line
                paragraph.space_before = Pt(0)
                paragraph.space_after = Pt(0)
                paragraph.font.name = font
                paragraph.font.size = Pt(element.get("size", 18) * 0.75)
                paragraph.font.bold = element.get("bold", False)
                paragraph.font.color.rgb = RGBColor.from_string(element.get("color", "000000").lstrip("#"))
                if element.get("align") == "center":
                    paragraph.alignment = PP_ALIGN.CENTER
                for run in paragraph.runs:
                    run._r.get_or_add_rPr().append(_xml("a:ea", typeface=font))
            _paint(shape, {"fill": "none"})
        elif kind == "image":
            from PIL import Image
            image_path = (project / element["asset"]).resolve()
            if not image_path.is_relative_to(project):
                raise ProjectError(f"图片越出项目目录：{element['asset']}")
            with Image.open(image_path) as image:
                image_width, image_height = image.size
            scale = min(width / image_width, height / image_height)
            actual_width, actual_height = image_width * scale, image_height * scale
            shape = shapes.add_picture(
                str(image_path),
                unit(x + (width - actual_width) / 2),
                unit(y + (height - actual_height) / 2),
                width=unit(actual_width),
                height=unit(actual_height),
            )
        elif kind in {"rect", "ellipse", "path"}:
            shape = shapes.add_shape(
                MSO_SHAPE.OVAL if kind == "ellipse" else MSO_SHAPE.RECTANGLE,
                unit(x),
                unit(y),
                unit(width),
                unit(height),
            )
            if kind == "path":
                properties = shape._element.spPr
                old = properties.find("{http://schemas.openxmlformats.org/drawingml/2006/main}prstGeom")
                properties.remove(old)
                geometry = _xml("a:custGeom")
                for name in ("avLst", "gdLst", "ahLst", "cxnLst"):
                    geometry.append(_xml("a:" + name))
                geometry.append(_xml("a:rect", l=0, t=0, r="r", b="b"))
                paths = _xml("a:pathLst")
                path = _xml("a:path", w=round(element["viewbox"][0] * 1000), h=round(element["viewbox"][1] * 1000))
                names = {"M": "moveTo", "L": "lnTo", "C": "cubicBezTo", "Q": "quadBezTo", "Z": "close"}
                for command in element["commands"]:
                    part = _xml("a:" + names[command[0]])
                    for index in range(1, len(command), 2):
                        part.append(_xml("a:pt", x=round(command[index] * 1000), y=round(command[index + 1] * 1000)))
                    path.append(part)
                paths.append(path)
                geometry.append(paths)
                properties.insert(1, geometry)
            _paint(shape, element)
        else:
            raise ProjectError(f"不支持的元素类型：{kind}")
        shape.name = element["id"]


def build_pptx(
    project: Path | str,
    plan: dict,
    layout: dict,
    output: Path | str,
) -> Path:
    errors = validate_deck(plan, layout)
    if errors:
        raise ProjectError("\n".join(errors))
    try:
        from pptx import Presentation
        from pptx.dml.color import RGBColor
        from pptx.util import Inches
    except ImportError as exc:
        raise ProjectError("缺少 python-pptx。安装：python -m pip install python-pptx") from exc
    project = Path(project).resolve()
    output = Path(output)
    if not output.is_absolute():
        output = project / output
    output = output.resolve()
    if not output.is_relative_to(project):
        raise ProjectError("PPTX 输出必须位于项目目录")
    canvas_width, canvas_height = layout["canvas"]
    presentation = Presentation()
    presentation.slide_width = Inches(canvas_width / 96)
    presentation.slide_height = Inches(canvas_height / 96)
    font = plan.get("theme", {}).get("font", "Microsoft YaHei")
    metadata = {slide["id"]: slide for slide in plan["slides"]}
    for slide_layout in layout["slides"]:
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        background = slide_layout.get("background", plan.get("background", "#FFFFFF"))
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = RGBColor.from_string(background.lstrip("#"))
        canvas_slide = dict(slide_layout, canvas=layout["canvas"])
        _add_nodes(slide.shapes, _resolve_connectors(canvas_slide), plan["texts"], project, font)
        notes = metadata.get(slide_layout["id"], {}).get("notes", "")
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
    output.parent.mkdir(parents=True, exist_ok=True)
    presentation.save(str(output))
    return output

