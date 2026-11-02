"""呈现层：document.json → DOCX（可选依赖 python-docx）。"""

from __future__ import annotations

import json
import re
from pathlib import Path

try:
    from docx import Document
    from docx.enum.section import WD_SECTION
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    DOCX_AVAILABLE = True
except ImportError:  # pragma: no cover
    DOCX_AVAILABLE = False


class RenderDependencyError(RuntimeError):
    pass


BODY_FONT = "宋体"
HEAD_FONT = "微软雅黑"
MONO_FONT = "Consolas"
INK = RGBColor(0x1F, 0x29, 0x37)
MUTED = RGBColor(0x6B, 0x72, 0x80)
FACT = RGBColor(0x2F, 0x5D, 0x8A)
INFERENCE = RGBColor(0xC0, 0x7A, 0x34)
OPTION = RGBColor(0x6F, 0x65, 0x9E)

TOKEN_RE = re.compile(r"(\*\*.+?\*\*|`[^`]+`|\[\^[a-z]-\d{4}\])")


def _require():
    if not DOCX_AVAILABLE:
        raise RenderDependencyError(
            "缺少 python-docx。安装：python -m pip install python-docx"
        )


def _set_run_font(run, name=BODY_FONT, size=10.5, bold=None, color=None):
    run.font.name = name
    if run._element.rPr is None:
        run._element.get_or_add_rPr()
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color is not None:
        run.font.color.rgb = color


def _shade_paragraph(paragraph, fill):
    pPr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    pPr.append(shd)


def _left_border(paragraph, color="C07A34"):
    pPr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    left = OxmlElement("w:left")
    left.set(qn("w:val"), "single")
    left.set(qn("w:sz"), "18")
    left.set(qn("w:space"), "6")
    left.set(qn("w:color"), color)
    borders.append(left)
    pPr.append(borders)


def _shade_cell(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def _repeat_header(row):
    trPr = row._tr.get_or_add_trPr()
    tblHeader = OxmlElement("w:tblHeader")
    tblHeader.set(qn("w:val"), "true")
    trPr.append(tblHeader)


def _page_number(paragraph):
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)


def _toc(doc):
    paragraph = doc.add_paragraph()
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = 'TOC \\o "1-3" \\h \\z \\u'
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = "右键“更新域”生成目录"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(separate)
    run._r.append(text)
    run._r.append(end)

    settings = doc.settings.element
    update = OxmlElement("w:updateFields")
    update.set(qn("w:val"), "true")
    settings.append(update)


def _add_inline(paragraph, text, size=10.5, color=INK, bold=False):
    for token in TOKEN_RE.split(text):
        if not token:
            continue
        if token.startswith("**") and token.endswith("**"):
            run = paragraph.add_run(token[2:-2])
            _set_run_font(run, BODY_FONT, size, True, color)
        elif token.startswith("`") and token.endswith("`"):
            run = paragraph.add_run(token[1:-1])
            _set_run_font(run, MONO_FONT, size - 1, False, color)
        elif re.fullmatch(r"\[\^[a-z]-\d{4}\]", token):
            ref = token[2:-1]
            run = paragraph.add_run(ref)
            _set_run_font(run, BODY_FONT, size - 1, False, RGBColor(0x2F, 0x5D, 0x8A))
            run.font.superscript = True
        else:
            run = paragraph.add_run(token)
            _set_run_font(run, BODY_FONT, size, bold, color)


def _badge_color(layer):
    return {"fact": FACT, "inference": INFERENCE, "option": OPTION}.get(layer, MUTED)


def _prefix_badge(paragraph, layer):
    label = {"fact": "事实", "inference": "推论", "option": "选项"}.get(layer)
    if not label:
        return
    run = paragraph.add_run(f"[{label}] ")
    _set_run_font(run, HEAD_FONT, 8, True, _badge_color(layer))


def _badge(doc, layer):
    label = {"fact": "事实", "inference": "推论", "option": "选项"}.get(layer)
    if not label:
        return
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(4)
    paragraph.paragraph_format.space_after = Pt(0)
    run = paragraph.add_run(f"[{label}]")
    _set_run_font(run, HEAD_FONT, 8, True, _badge_color(layer))


def _add_table(doc, block):
    columns = block.get("columns", [])
    rows = block.get("rows", [])
    if not columns:
        return
    table = doc.add_table(rows=1, cols=len(columns))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    header = table.rows[0]
    _repeat_header(header)
    for index, name in enumerate(columns):
        cell = header.cells[index]
        cell.text = ""
        paragraph = cell.paragraphs[0]
        run = paragraph.add_run(name)
        _set_run_font(run, HEAD_FONT, 9, True, INK)
        _shade_cell(cell, "F3F4F6")
    for row in rows:
        cells = table.add_row().cells
        for index, value in enumerate(row[: len(columns)]):
            cell = cells[index]
            cell.text = ""
            paragraph = cell.paragraphs[0]
            _add_inline(paragraph, value, 9)
    doc.add_paragraph()


def _add_figure(doc, block, project):
    path = (project / block["src"]).resolve()
    if not path.exists():
        paragraph = doc.add_paragraph()
        run = paragraph.add_run(f"图片缺失：{block['src']}")
        _set_run_font(run, BODY_FONT, 9, False, MUTED)
        return
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    run.add_picture(str(path), width=Cm(16))
    caption = doc.add_paragraph()
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    label = block.get("caption", "") or "图"
    run = caption.add_run(f"图 · {label}")
    _set_run_font(run, BODY_FONT, 9, False, MUTED)


def _add_callout(doc, block, layer="inference"):
    paragraph = doc.add_paragraph()
    _shade_paragraph(paragraph, "FDFAF5")
    _left_border(paragraph)
    _prefix_badge(paragraph, layer)
    _add_inline(paragraph, block.get("text", ""), 10)


def _add_code(doc, block):
    paragraph = doc.add_paragraph()
    _shade_paragraph(paragraph, "F3F4F6")
    run = paragraph.add_run(block.get("text", ""))
    _set_run_font(run, MONO_FONT, 9, False, INK)


def _add_references(doc, document):
    doc.add_page_break()
    heading = doc.add_heading("来源与引用", level=1)
    _style_heading(heading, 1)
    sources = {item["id"]: item for item in document.get("sources", [])}
    footnotes = document.get("footnotes", {})
    for ref_id in sorted(set(sources) | set(footnotes)):
        source = sources.get(ref_id, {})
        paragraph = doc.add_paragraph()
        run = paragraph.add_run(f"[{ref_id}] ")
        _set_run_font(run, MONO_FONT, 9, True, FACT)
        run = paragraph.add_run(source.get("title") or footnotes.get(ref_id, ""))
        _set_run_font(run, BODY_FONT, 9, False, INK)
        meta = " · ".join(
            part for part in (source.get("publisher"), source.get("grade")) if part
        )
        if meta:
            run = paragraph.add_run(f"  {meta}")
            _set_run_font(run, BODY_FONT, 8, False, MUTED)
        if source.get("locator"):
            run = paragraph.add_run(f"  {source['locator']}")
            _set_run_font(run, BODY_FONT, 8, False, MUTED)


def _style_heading(paragraph, level):
    size = {1: 18, 2: 14, 3: 12, 4: 11}.get(level, 11)
    for run in paragraph.runs:
        _set_run_font(run, HEAD_FONT, size, True, INK)
    paragraph.paragraph_format.space_before = Pt(12 if level <= 2 else 8)
    paragraph.paragraph_format.space_after = Pt(6)


def _setup_document(document):
    doc = Document()
    section = doc.sections[0]
    section.page_height = Cm(29.7)
    section.page_width = Cm(21.0)
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.2)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.2)

    normal = doc.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
    normal.paragraph_format.line_spacing = 1.5
    normal.paragraph_format.space_after = Pt(4)

    for level in range(1, 5):
        style = doc.styles[f"Heading {level}"]
        style.font.name = HEAD_FONT
        style.element.rPr.rFonts.set(qn("w:eastAsia"), HEAD_FONT)
        style.font.color.rgb = INK
        style.font.bold = True

    header = section.header.paragraphs[0]
    run = header.add_run(document.get("title", ""))
    _set_run_font(run, HEAD_FONT, 8, False, MUTED)
    header.add_run("\t\t")
    run = header.add_run(document.get("version", ""))
    _set_run_font(run, HEAD_FONT, 8, False, MUTED)

    footer = section.footer.paragraphs[0]
    run = footer.add_run(f"{document.get('project', '')} · 内部 · ")
    _set_run_font(run, BODY_FONT, 8, False, MUTED)
    _page_number(footer)

    doc.core_properties.title = document.get("title", "")
    doc.core_properties.subject = document.get("project", "")
    doc.core_properties.comments = "决策支持材料；按事实/推论/选项三层组织。"
    return doc


def render_docx(project: Path, document: dict | None = None, *, output: Path | str | None = None) -> Path:
    _require()
    project = project.resolve()
    if document is None:
        doc_path = project / "report" / "document.json"
        if not doc_path.exists():
            raise FileNotFoundError("缺少 report/document.json，请先运行 render build")
        document = json.loads(doc_path.read_text(encoding="utf-8"))

    doc = _setup_document(document)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = title.add_run(document.get("title", "研究报告"))
    _set_run_font(run, HEAD_FONT, 24, True, INK)
    title.paragraph_format.space_after = Pt(6)

    meta = doc.add_paragraph()
    run = meta.add_run(
        f"{document.get('version', '')}  |  as-of {document.get('as_of', '')}  |  "
        f"{document.get('project', '')}"
    )
    _set_run_font(run, BODY_FONT, 9, False, MUTED)

    notice = doc.add_paragraph()
    _shade_paragraph(notice, "F7F9FC")
    run = notice.add_run(
        "决策支持材料：按事实（带来源）、推论（标假设）、选项（对称呈现，不排名）三层组织；"
        "最终选择由读者按自身目标决定。"
    )
    _set_run_font(run, BODY_FONT, 9, False, MUTED)

    doc.add_page_break()
    _toc(doc)
    doc.add_page_break()

    for section in document.get("sections", []):
        level = section.get("level", 2)
        if level == 1 and section is not document["sections"][0]:
            doc.add_page_break()
        heading = doc.add_heading(section.get("title", ""), level=min(level, 4))
        _style_heading(heading, level)

        for block in section.get("blocks", []):
            kind = block.get("type")
            layer = block.get("layer", "fact")
            if kind == "heading":
                heading = doc.add_heading(block.get("text", ""), level=min(block.get("level", 3), 4))
                _style_heading(heading, block.get("level", 3))
            elif kind == "paragraph":
                paragraph = doc.add_paragraph()
                _prefix_badge(paragraph, layer)
                _add_inline(paragraph, block.get("text", ""))
            elif kind == "callout":
                _add_callout(doc, block, layer)
            elif kind == "list":
                style = "List Number" if block.get("ordered") else "List Bullet"
                for index, item in enumerate(block.get("items", [])):
                    paragraph = doc.add_paragraph(style=style)
                    if index == 0:
                        _prefix_badge(paragraph, layer)
                    _add_inline(paragraph, item)
            elif kind == "table":
                if layer != "fact":
                    _badge(doc, layer)
                _add_table(doc, block)
            elif kind == "figure":
                _add_figure(doc, block, project)
            elif kind == "code":
                _add_code(doc, block)

    _add_references(doc, document)
    out = Path(output) if output is not None else project / "report" / "report.docx"
    if not out.is_absolute():
        out = project / out
    out = out.resolve()
    if not out.is_relative_to(project):
        raise ValueError("DOCX 输出必须位于项目目录")
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    return out
