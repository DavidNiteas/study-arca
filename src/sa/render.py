"""呈现层：Markdown → document.json → 自包含 HTML。"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
from pathlib import Path

CITE_RE = re.compile(r"\[\^([a-z]-\d{4})\]")
HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$")
IMAGE_RE = re.compile(r"^!\[(.*?)\]\((.*?)\)\s*$")
FOOTNOTE_RE = re.compile(r"^\[\^([a-z]-\d{4})\]:\s*(.*)$")
VERSION_RE = re.compile(r"版本[：:]\s*([^\s｜|]+)")
ASOF_RE = re.compile(r"as-of[：:]\s*([0-9-]+)", re.I)
PROJECT_RE = re.compile(r"`(p-\d{8}-[a-z0-9-]+)`")

MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml"}


def latest_report(project: Path) -> Path | None:
    reports = sorted((project / "deliverables" / "report").glob("v*/report.md"))
    if not reports:
        return None

    def key(path: Path):
        match = re.search(r"v(\d+)\.(\d+)", path.parent.name)
        return (int(match.group(1)), int(match.group(2))) if match else (0, 0)

    return max(reports, key=key)


def _inline(text: str) -> str:
    value = html.escape(text, quote=False)
    value = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", value)
    value = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", value)
    value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
    value = CITE_RE.sub(
        lambda m: f'<sup><a class="cite" href="#ref-{m.group(1)}" data-ref="{m.group(1)}">{m.group(1)}</a></sup>',
        value,
    )
    value = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', value)
    return value


def _split_row(line: str) -> list[str]:
    cells = line.strip().strip("|").split("|")
    return [cell.strip() for cell in cells]


def _is_separator(line: str) -> bool:
    cells = _split_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", cell.replace(" ", "")) for cell in cells)


def _classify(text: str, part: str, section: str, kind: str) -> str:
    if section == "导读":
        return "fact"
    if kind in {"table", "figure"}:
        if "第三部分" in part and ("可选路径" in section or "选项" in section):
            return "option"
        return "fact"
    if kind == "callout":
        return "inference"
    if "第三部分" in part or "推论" in section or "可选路径" in section:
        if any(key in text for key in ("路径", "选项", "条件", "不成立", "代价", "所需资源")):
            return "option"
        return "inference"
    if any(key in text for key in ("假设", "推断", "模型输出", "置信度", "条件式", "条件判断")):
        return "inference"
    return "fact"


def parse_markdown(text: str) -> dict:
    lines = text.splitlines()
    title = ""
    meta_callout: list[str] = []
    sections: list[dict] = []
    footnotes: dict[str, str] = {}
    current_section: dict | None = None
    current_part = ""
    buffer: list[str] = []
    i = 0

    def flush_paragraph():
        nonlocal buffer
        if not buffer:
            return
        paragraph = " ".join(item.strip() for item in buffer).strip()
        buffer = []
        if not paragraph:
            return
        if current_section is None:
            return
        current_section["blocks"].append(
            {
                "type": "paragraph",
                "layer": _classify(paragraph, current_part, current_section["title"], "paragraph"),
                "text": paragraph,
            }
        )

    def new_section(title_text: str, level: int):
        nonlocal current_section
        flush_paragraph()
        current_section = {
            "id": "",
            "title": title_text,
            "level": level,
            "blocks": [],
        }
        sections.append(current_section)

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            i += 1
            code_lines = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1
            if current_section is not None:
                current_section["blocks"].append(
                    {"type": "code", "layer": "fact", "text": "\n".join(code_lines)}
                )
            continue

        if not stripped:
            flush_paragraph()
            i += 1
            continue

        if stripped == "---":
            flush_paragraph()
            i += 1
            continue

        footnote = FOOTNOTE_RE.match(stripped)
        if footnote:
            flush_paragraph()
            footnotes[footnote.group(1)] = footnote.group(2).strip()
            i += 1
            continue

        heading = HEADING_RE.match(stripped)
        if heading:
            level = len(heading.group(1))
            heading_text = heading.group(2).strip()
            if level == 1 and not title:
                title = heading_text
                i += 1
                continue
            if level == 1:
                current_part = heading_text
                new_section(heading_text, 1)
            elif level == 2:
                new_section(heading_text, 2)
            else:
                flush_paragraph()
                if current_section is not None:
                    current_section["blocks"].append(
                        {"type": "heading", "level": level, "text": heading_text}
                    )
            i += 1
            continue

        image = IMAGE_RE.match(stripped)
        if image:
            flush_paragraph()
            if current_section is not None:
                current_section["blocks"].append(
                    {
                        "type": "figure",
                        "layer": "fact",
                        "src": image.group(2).strip(),
                        "caption": image.group(1).strip(),
                    }
                )
            i += 1
            continue

        if stripped.startswith("|"):
            flush_paragraph()
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            if len(table_lines) >= 2:
                headers = _split_row(table_lines[0])
                body_start = 2 if _is_separator(table_lines[1]) else 1
                rows = [_split_row(row) for row in table_lines[body_start:]]
                if current_section is not None:
                    table_text = " ".join(headers) + " " + " ".join(
                        " ".join(row) for row in rows
                    )
                    current_section["blocks"].append(
                        {
                            "type": "table",
                            "layer": _classify(
                                table_text,
                                current_part,
                                current_section["title"],
                                "table",
                            ),
                            "columns": headers,
                            "rows": rows,
                        }
                    )
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            quote = " ".join(quote_lines).strip()
            if quote:
                if not sections and not meta_callout:
                    meta_callout = quote_lines
                if current_section is not None:
                    current_section["blocks"].append(
                        {
                            "type": "callout",
                            "layer": "inference",
                            "text": quote,
                        }
                    )
            continue

        if re.match(r"^(-|\d+\.)\s+", stripped):
            flush_paragraph()
            items = []
            ordered = bool(re.match(r"^\d+\.", stripped))
            while i < len(lines) and re.match(r"^(-|\d+\.)\s+", lines[i].strip()):
                item = re.sub(r"^(-|\d+\.)\s+", "", lines[i].strip())
                items.append(item)
                i += 1
            if current_section is not None:
                joined = " ".join(items)
                current_section["blocks"].append(
                    {
                        "type": "list",
                        "layer": _classify(joined, current_part, current_section["title"], "list"),
                        "ordered": ordered,
                        "items": items,
                    }
                )
            continue

        buffer.append(stripped)
        i += 1

    flush_paragraph()

    for index, section in enumerate(sections):
        section["id"] = f"s{index + 1}"

    meta_text = " ".join(meta_callout)
    version_match = VERSION_RE.search(meta_text)
    asof_match = ASOF_RE.search(meta_text)
    project_match = PROJECT_RE.search(meta_text)

    return {
        "schema": "sa.document/1",
        "title": title,
        "version": version_match.group(1) if version_match else "",
        "as_of": asof_match.group(1) if asof_match else "",
        "project": project_match.group(1) if project_match else "",
        "meta": meta_callout,
        "sections": sections,
        "footnotes": footnotes,
    }


def _load_sources(project: Path) -> list[dict]:
    sources = []
    for meta_file in sorted((project / "search").glob("s-*/meta.json")):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        sources.append(
            {
                "id": meta.get("id", ""),
                "title": meta.get("title", ""),
                "publisher": meta.get("publisher", ""),
                "grade": meta.get("evidence_grade", ""),
                "locator": meta.get("locator", ""),
                "retrieved_at": meta.get("retrieved_at", ""),
                "source_type": meta.get("source_type", ""),
                "tool": meta.get("tool", ""),
            }
        )
    return sources


def build_document(project: Path, source_md: Path | None = None) -> dict:
    project = project.resolve()
    if source_md is None:
        source_md = latest_report(project)
    elif not source_md.is_absolute():
        candidate = source_md if source_md.exists() else project / source_md
        source_md = candidate.resolve()
    if source_md is None or not source_md.exists():
        raise FileNotFoundError("找不到报告 Markdown（deliverables/report/v*/report.md）")
    parsed = parse_markdown(source_md.read_text(encoding="utf-8"))

    project_meta_path = project / "project.json"
    project_meta = {}
    if project_meta_path.exists():
        project_meta = json.loads(project_meta_path.read_text(encoding="utf-8"))

    for section in parsed["sections"]:
        for block in section["blocks"]:
            if block["type"] == "figure":
                raw = (source_md.parent / block["src"]).resolve()
                try:
                    block["src"] = raw.relative_to(project.resolve()).as_posix()
                except ValueError:
                    block["src"] = str(raw)

    parsed["project"] = parsed.get("project") or project_meta.get("id", project.name)
    parsed["generated_from"] = str(source_md.relative_to(project.resolve())).replace("\\", "/")
    parsed["layer_source"] = "heuristic"
    parsed["sources"] = _load_sources(project)
    return parsed


def write_document(project: Path, document: dict) -> Path:
    out = project / "report" / "document.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def _data_uri(path: Path) -> str | None:
    if not path.exists():
        return None
    mime = MIME.get(path.suffix.lower(), "application/octet-stream")
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def _layer_badge(layer: str) -> str:
    return {
        "fact": '<span class="badge fact">事实</span>',
        "inference": '<span class="badge inference">推论</span>',
        "option": '<span class="badge option">选项</span>',
    }.get(layer, "")


def _render_table(block: dict) -> str:
    head = "".join(f"<th>{_inline(cell)}</th>" for cell in block["columns"])
    body = "".join(
        "<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in row) + "</tr>"
        for row in block["rows"]
    )
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _render_block(block: dict, project: Path) -> str:
    kind = block["type"]
    layer = block.get("layer", "fact")
    attrs = f'data-layer="{layer}"'
    if kind == "heading":
        level = block["level"]
        return f'<h{level} class="block subheading" {attrs}>{_inline(block["text"])}</h{level}>'
    if kind == "paragraph":
        return f'<p class="block" {attrs}>{_layer_badge(layer)}{_inline(block["text"])}</p>'
    if kind == "callout":
        return (
            f'<div class="block callout" {attrs}>{_layer_badge(layer)}'
            f'<div>{_inline(block["text"])}</div></div>'
        )
    if kind == "list":
        tag = "ol" if block.get("ordered") else "ul"
        items = "".join(f"<li>{_inline(item)}</li>" for item in block["items"])
        return f'<{tag} class="block" {attrs}>{_layer_badge(layer)}{items}</{tag}>'
    if kind == "table":
        return f'<div class="block" {attrs}>{_layer_badge(layer)}{_render_table(block)}</div>'
    if kind == "figure":
        path = (project / block["src"]).resolve()
        uri = _data_uri(path)
        if uri is None:
            body = f'<div class="missing">图片缺失：{html.escape(block["src"])}</div>'
        else:
            body = f'<img src="{uri}" alt="{html.escape(block.get("caption", ""))}">'
        return (
            f'<figure class="block" {attrs}>{_layer_badge(layer)}{body}'
            f'<figcaption>{_inline(block.get("caption", ""))}</figcaption></figure>'
        )
    if kind == "code":
        return f'<pre class="block" {attrs}><code>{html.escape(block["text"])}</code></pre>'
    return ""


def _toc(document: dict) -> str:
    items = []
    for section in document["sections"]:
        if section["level"] == 1:
            items.append(f'<a class="toc-part" href="#{section["id"]}">{html.escape(section["title"])}</a>')
        else:
            items.append(f'<a class="toc-sub" href="#{section["id"]}">{html.escape(section["title"])}</a>')
    return "".join(items)


def _references(document: dict, project: Path) -> str:
    sources = {source["id"]: source for source in document.get("sources", [])}
    footnotes = document.get("footnotes", {})
    ids = sorted(set(sources) | set(footnotes))
    rows = []
    for ref_id in ids:
        source = sources.get(ref_id, {})
        text = footnotes.get(ref_id, "")
        title = source.get("title") or text or ref_id
        grade = source.get("grade", "")
        publisher = source.get("publisher", "")
        locator = source.get("locator", "")
        link = f'<a href="{html.escape(locator)}" target="_blank" rel="noopener">链接</a>' if locator else ""
        rows.append(
            f'<li id="ref-{ref_id}"><code>{ref_id}</code> '
            f'<strong>{html.escape(title)}</strong>'
            f'<span class="ref-meta">{html.escape(publisher)} {grade}</span>{link}'
            f'<div class="ref-note">{_inline(text)}</div></li>'
        )
    return '<ol class="refs">' + "".join(rows) + "</ol>"


def render_html(project: Path, document: dict | None = None) -> Path:
    project = project.resolve()
    if document is None:
        doc_path = project / "report" / "document.json"
        if not doc_path.exists():
            document = build_document(project)
        else:
            document = json.loads(doc_path.read_text(encoding="utf-8"))

    sections_html = []
    for section in document["sections"]:
        blocks = "".join(_render_block(block, project) for block in section["blocks"])
        tag = "section" if section["level"] == 1 else "section"
        sections_html.append(
            f'<{tag} id="{section["id"]}" class="doc-section level-{section["level"]}">'
            f'<h{section["level"]}>{_inline(section["title"])}</h{section["level"]}>{blocks}</{tag}>'
        )

    sources_json = json.dumps(
        {source["id"]: source for source in document.get("sources", [])},
        ensure_ascii=False,
    ).replace("</", "<\\/")
    footnotes_json = json.dumps(document.get("footnotes", {}), ensure_ascii=False).replace("</", "<\\/")

    title = html.escape(document.get("title", "研究报告"))
    version = html.escape(document.get("version", ""))
    as_of = html.escape(document.get("as_of", ""))
    project_id = html.escape(document.get("project", ""))
    generated = html.escape(document.get("generated_from", ""))

    css = """
:root{--ink:#1f2937;--muted:#6b7280;--line:#e5e7eb;--bg:#ffffff;--soft:#f8fafc;
--fact:#2f5d8a;--inference:#c07a34;--option:#6f659e;--accent:#2f5d8a}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font-family:"Microsoft YaHei","PingFang SC","Noto Sans CJK SC",sans-serif;line-height:1.75;font-size:15.5px}
a{color:var(--accent)}
.layout{display:grid;grid-template-columns:240px minmax(0,1fr);max-width:1320px;margin:0 auto;gap:36px;padding:0 28px}
.sidebar{position:sticky;top:0;align-self:start;max-height:100vh;overflow:auto;padding:28px 0 40px;border-right:1px solid var(--line)}
.sidebar .brand{font-size:13px;color:var(--muted);letter-spacing:.08em;margin-bottom:18px}
.toc{display:flex;flex-direction:column;gap:4px;font-size:13px}
.toc a{text-decoration:none;color:var(--muted);padding:3px 8px;border-radius:6px}
.toc a:hover{background:var(--soft);color:var(--ink)}
.toc-part{font-weight:700;color:var(--ink)!important;margin-top:10px}
.toc-sub{padding-left:20px!important}
main{padding:44px 0 80px;min-width:0}
.kicker{font-size:12px;letter-spacing:.14em;color:var(--accent);font-weight:700;text-transform:uppercase}
h1{font-size:34px;line-height:1.3;margin:8px 0 14px}
.doc-meta{color:var(--muted);font-size:12.5px;display:flex;gap:14px;flex-wrap:wrap;margin-bottom:18px}
.notice{border:1px solid #dce3ec;background:#f7f9fc;border-radius:10px;padding:12px 16px;font-size:12.5px;color:#4b5563;margin:18px 0 26px}
.toolbar{position:sticky;top:0;z-index:20;background:rgba(255,255,255,.96);backdrop-filter:blur(6px);border-bottom:1px solid var(--line);padding:10px 0;display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:22px}
.toolbar button,.toolbar input{font:inherit;font-size:13px;border:1px solid var(--line);background:#fff;border-radius:8px;padding:6px 12px;color:var(--ink);cursor:pointer}
.toolbar button.active{background:var(--ink);color:#fff;border-color:var(--ink)}
.toolbar input{flex:1;min-width:180px;cursor:text}
.doc-section{margin:0 0 34px;scroll-margin-top:80px}
.doc-section.level-1{margin-top:52px;padding-top:10px;border-top:2px solid var(--ink)}
.doc-section.level-1>h1{font-size:28px}
.doc-section.level-2>h2{font-size:21px;margin:26px 0 10px}
h3{font-size:17px;margin:20px 0 8px}
h4{font-size:15px;margin:16px 0 6px}
p{margin:10px 0}
.block{position:relative}
.badge{display:inline-block;font-size:10px;line-height:1;padding:3px 6px;border-radius:4px;margin-right:6px;vertical-align:2px;font-weight:700;letter-spacing:.04em}
.badge.fact{background:#e8f0f8;color:var(--fact)}
.badge.inference{background:#faf0e2;color:var(--inference)}
.badge.option{background:#f0ecf7;color:var(--option)}
.callout{border-left:4px solid var(--inference);background:#fdfaf5;padding:10px 14px;border-radius:0 8px 8px 0;margin:12px 0}
code{background:#f3f4f6;padding:2px 5px;border-radius:4px;font-size:90%}
pre{background:#0f172a;color:#e5e7eb;padding:14px 16px;border-radius:8px;overflow:auto;font-size:12.5px;line-height:1.6}
pre code{background:none;padding:0;color:inherit}
.table-wrap{overflow:auto;margin:12px 0;border:1px solid var(--line);border-radius:8px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border-bottom:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}
th{background:var(--soft);font-weight:700;white-space:nowrap}
tbody tr:last-child td{border-bottom:none}
figure{margin:18px 0;text-align:center}
figure img{max-width:100%;height:auto;border:1px solid var(--line);border-radius:6px;background:#fff}
figcaption{font-size:12px;color:var(--muted);margin-top:6px}
.missing{padding:24px;border:1px dashed #cbd5e1;color:var(--muted);border-radius:8px}
sup .cite{font-size:10px;text-decoration:none;background:#eef2f7;color:var(--fact);padding:1px 4px;border-radius:3px}
.refs{font-size:12.5px;color:#374151}
.refs li{margin:8px 0}
.ref-meta{color:var(--muted);margin-left:8px;font-size:11px}
.ref-note{color:var(--muted);font-size:11.5px}
.drawer{position:fixed;top:0;right:0;width:380px;max-width:92vw;height:100vh;background:#fff;border-left:1px solid var(--line);box-shadow:-12px 0 30px rgba(15,23,42,.12);padding:24px;transform:translateX(105%);transition:transform .18s ease;z-index:50;overflow:auto}
.drawer.open{transform:translateX(0)}
.drawer h3{margin-top:0}
.drawer .close{position:absolute;top:14px;right:14px;border:none;background:var(--soft);border-radius:6px;padding:4px 9px;cursor:pointer}
body[data-layer-mode="fact"] .block[data-layer="inference"],body[data-layer-mode="fact"] .block[data-layer="option"],
body[data-layer-mode="inference"] .block[data-layer="fact"],body[data-layer-mode="inference"] .block[data-layer="option"],
body[data-layer-mode="option"] .block[data-layer="fact"],body[data-layer-mode="option"] .block[data-layer="inference"]{display:none}
body[data-layer-mode="fact"] .block[data-layer="fact"] .badge,
body[data-layer-mode="inference"] .block[data-layer="inference"] .badge,
body[data-layer-mode="option"] .block[data-layer="option"] .badge{display:none}
footer{border-top:1px solid var(--line);margin-top:50px;padding-top:16px;color:var(--muted);font-size:11.5px}
@media (max-width:900px){.layout{display:block}.sidebar{position:static;max-height:none;border-right:none;border-bottom:1px solid var(--line);padding-bottom:16px}main{padding-top:24px}}
@media print{.sidebar,.toolbar,.drawer{display:none!important}.layout{display:block;max-width:none;padding:0}body[data-layer-mode] .block{display:block!important}.doc-section.level-1{page-break-before:always}figure img{max-width:100%}}
"""

    js = """
const SOURCES = __SOURCES__;
const FOOTNOTES = __FOOTNOTES__;
const drawer = document.getElementById('drawer');
const drawerBody = document.getElementById('drawer-body');
function openRef(id){
  const s = SOURCES[id] || {};
  const note = FOOTNOTES[id] || '';
  drawerBody.innerHTML = `<div class="kicker">来源 ${id}</div>`+
    `<h3>${s.title || id}</h3>`+
    `<p>${s.publisher || ''} ${s.grade ? '· '+s.grade : ''}</p>`+
    `<p>${s.locator ? '<a href="'+s.locator+'" target="_blank" rel="noopener">'+s.locator+'</a>' : ''}</p>`+
    `<p>${note}</p>`;
  drawer.classList.add('open');
}
document.querySelectorAll('.cite').forEach(a=>{
  a.addEventListener('click',e=>{e.preventDefault();openRef(a.dataset.ref);});
});
document.getElementById('drawer-close').addEventListener('click',()=>drawer.classList.remove('open'));
document.addEventListener('keydown',e=>{if(e.key==='Escape')drawer.classList.remove('open');});
document.querySelectorAll('[data-layer-btn]').forEach(btn=>{
  btn.addEventListener('click',()=>{
    document.body.dataset.layerMode = btn.dataset.layerBtn;
    document.querySelectorAll('[data-layer-btn]').forEach(b=>b.classList.toggle('active',b===btn));
    syncSections();
  });
});
function syncSections(){
  const mode = document.body.dataset.layerMode;
  const secs = Array.from(document.querySelectorAll('.doc-section'));
  document.querySelectorAll('.block').forEach(b=>{b.style.display='';});
  const own = new Map();
  secs.forEach(sec=>{
    const blocks = sec.querySelectorAll('.block');
    own.set(sec, mode === 'all' || Array.from(blocks).some(b=>b.dataset.layer === mode));
  });
  secs.forEach((sec, index)=>{
    if(sec.classList.contains('level-1')){
      let show = own.get(sec);
      for(let j=index+1; j<secs.length && !secs[j].classList.contains('level-1'); j++){
        if(own.get(secs[j])){ show = true; break; }
      }
      sec.style.display = show ? '' : 'none';
    } else {
      sec.style.display = own.get(sec) ? '' : 'none';
    }
  });
}
syncSections();
document.getElementById('search').addEventListener('input',e=>{
  const q = e.target.value.trim().toLowerCase();
  if(!q){ syncSections(); return; }
  document.querySelectorAll('.doc-section').forEach(sec=>{
    let visible = 0;
    sec.querySelectorAll('.block').forEach(block=>{
      const hit = !q || block.textContent.toLowerCase().includes(q);
      block.style.display = hit ? '' : 'none';
      if(hit) visible++;
    });
    if(q) sec.style.display = visible ? '' : 'none';
    else sec.style.display = '';
  });
});
document.getElementById('print').addEventListener('click',()=>window.print());
"""

    js = js.replace("__SOURCES__", sources_json).replace("__FOOTNOTES__", footnotes_json)
    body = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · {version}</title>
<style>{css}</style>
</head>
<body data-layer-mode="all">
<div class="layout">
<aside class="sidebar">
<div class="brand">SEARCH-ANALYSIS · 研究版</div>
<nav class="toc">{_toc(document)}</nav>
</aside>
<main>
<div class="kicker">决策支持材料 · 不含建议</div>
<h1>{title}</h1>
<div class="doc-meta"><span>{version}</span><span>as-of {as_of}</span><span>{project_id}</span></div>
<div class="notice">本材料按三层组织：<strong>事实</strong>（带来源）、<strong>推论</strong>（标假设）、<strong>选项</strong>（对称呈现，不排名）。最终选择由读者按自身目标决定。</div>
<div class="toolbar">
<button data-layer-btn="all" class="active">全部</button>
<button data-layer-btn="fact">事实</button>
<button data-layer-btn="inference">推论</button>
<button data-layer-btn="option">选项</button>
<input id="search" type="search" placeholder="搜索本报告…">
<button id="print">打印 / PDF</button>
</div>
{''.join(sections_html)}
<section class="doc-section level-1" id="refs"><h1>来源与引用</h1>{_references(document, project)}</section>
<footer>生成自 {generated} ｜ 结构 {html.escape(document.get('schema',''))} ｜ 层标注为 {html.escape(document.get('layer_source',''))}，需人工复核。</footer>
</main>
</div>
<div class="drawer" id="drawer"><button class="close" id="drawer-close">关闭</button><div id="drawer-body"></div></div>
<script>{js}</script>
</body>
</html>
"""
    out = project / "report" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    return out
