"""项目脚手架与来源信封。"""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_TEMPLATE = REPO_ROOT / "templates" / "project"

REQUIRED_DIRS = [
    "brief",
    "_dev",
    "search",
    "tools",
    "analysis/datasets",
    "analysis/notes",
    "analysis/findings",
    "report",
    "deliverables/report",
    "deliverables/deck",
]

TEXT_SUFFIXES = {".md", ".json", ".jsonl", ".txt", ".yaml", ".yml"}
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PROJECT_ID_RE = re.compile(r"^p-\d{8}-[a-z0-9-]+$")

SOURCE_TYPES = {
    "gov", "database", "filing", "paper", "web", "interview", "internal",
}
EVIDENCE_GRADES = {"E1", "E2", "E3", "E4"}


class ProjectError(Exception):
    pass


def _now() -> datetime:
    return datetime.now().astimezone()


def _short_id(number: int) -> str:
    return f"{number:04d}"


def slugify(text: str, fallback: str = "source") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if not re.search(r"[a-z]", slug):
        return fallback
    return slug


def _ensure_keep(path: Path) -> None:
    """空目录放 .gitkeep；已有内容的目录清掉多余的 .gitkeep。"""
    path.mkdir(parents=True, exist_ok=True)
    keep = path / ".gitkeep"
    has_content = any(child.name != ".gitkeep" for child in path.iterdir())
    if has_content and keep.exists():
        keep.unlink()
    elif not has_content and not keep.exists():
        keep.write_text("", encoding="utf-8")


def new_project(
    slug: str,
    title: str | None = None,
    root: Path | str | None = None,
    date: str | None = None,
    git: bool = True,
    workflow: str = "legacy",
) -> Path:
    if workflow not in {"legacy", "cycle"}:
        raise ProjectError("workflow 必须是 legacy/cycle")
    if not SLUG_RE.match(slug):
        raise ProjectError("slug 只能是小写字母/数字/连字符，且以字母或数字开头")
    now = _now()
    day = date or now.strftime("%Y-%m-%d")
    compact = day.replace("-", "")
    project_id = f"p-{compact}-{slug}"
    root_path = Path(root) if root else REPO_ROOT / "workspace"
    dest = root_path / project_id
    if dest.exists():
        raise ProjectError(f"目录已存在：{dest}")
    if not PROJECT_TEMPLATE.is_dir():
        raise ProjectError(f"找不到模板：{PROJECT_TEMPLATE}")

    root_path.mkdir(parents=True, exist_ok=True)
    shutil.copytree(PROJECT_TEMPLATE, dest, ignore=shutil.ignore_patterns("_dev") if workflow == "cycle" else None)

    replacements = {
        "{{ID}}": project_id,
        "{{TITLE}}": title or slug,
        "{{DATE}}": day,
        "{{SLUG}}": slug,
    }
    for path in dest.rglob("*"):
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8")
            for key, value in replacements.items():
                text = text.replace(key, value)
            path.write_text(text, encoding="utf-8")

    for rel in REQUIRED_DIRS:
        if workflow == "cycle" and rel == "_dev":
            continue
        _ensure_keep(dest / rel)
    if workflow == "cycle":
        meta = load_json(dest / "project.json")
        meta["workflow"] = "sa.research/1"
        meta["status"] = "active"
        for field in ("gate_waivers", "question", "out_of_scope", "acceptance"):
            meta.pop(field, None)
        save_json(dest / "project.json", meta)
        from .cycle import init_cycle
        init_cycle(dest)
    (dest / "search" / "queries.jsonl").touch()
    if git:
        _init_git(dest, project_id)
    return dest


def _init_git(dest: Path, project_id: str) -> None:
    """项目级独立仓库：每个调研一个 git，互不共享历史。"""
    import subprocess

    if not shutil.which("git"):
        print("[WARN ] 未找到 git，跳过仓库初始化", file=sys.stderr)
        return
    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    identity = (
        subprocess.run(["git", "config", "user.name"], cwd=dest, capture_output=True, text=True)
        .stdout.strip()
    ) and (
        subprocess.run(["git", "config", "user.email"], cwd=dest, capture_output=True, text=True)
        .stdout.strip()
    )
    if not identity:
        print("[WARN ] 未配置 git 身份，已 init 但未提交；配置后 git add -A && git commit", file=sys.stderr)
        return
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", f"chore: 初始化调研项目 {project_id}"],
        cwd=dest,
        check=True,
    )


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def next_source_number(project: Path) -> int:
    numbers = []
    search = project / "search"
    if search.is_dir():
        for child in search.iterdir():
            match = re.match(r"^s-(\d{4})-", child.name)
            if match and child.is_dir():
                numbers.append(int(match.group(1)))
    return max(numbers, default=0) + 1


def add_source(
    project: Path | str,
    title: str,
    tool: str,
    locator: str,
    publisher: str,
    grade: str,
    query: str = "",
    source_type: str = "web",
    license_text: str = "",
    notes: str = "",
    slug: str | None = None,
    extracted: str | None = None,
) -> Path:
    project = Path(project)
    if not (project / "project.json").exists():
        raise ProjectError(f"不是有效项目目录：{project}")
    if grade not in EVIDENCE_GRADES:
        raise ProjectError(f"evidence_grade 必须是 {sorted(EVIDENCE_GRADES)}")
    if source_type not in SOURCE_TYPES:
        raise ProjectError(f"source_type 必须是 {sorted(SOURCE_TYPES)}")

    number = next_source_number(project)
    source_id = f"s-{_short_id(number)}"
    directory = project / "search" / f"{source_id}-{slug or slugify(title)}"
    if directory.exists():
        raise ProjectError(f"来源目录已存在：{directory}")
    (directory / "raw").mkdir(parents=True)

    now = _now().isoformat(timespec="seconds")
    meta = {
        "id": source_id,
        "title": title,
        "source_type": source_type,
        "tool": tool,
        "query": {"text": query, "params": {}},
        "locator": locator,
        "publisher": publisher,
        "published_at": None,
        "retrieved_at": now,
        "period": {"start": None, "end": None},
        "evidence_grade": grade,
        "license": license_text,
        "raw": [],
        "notes": notes,
    }
    save_json(directory / "meta.json", meta)

    (directory / "extracted.md").write_text(
        extracted
        if extracted is not None
        else (
            f"# {source_id} · {title}\n\n"
            f"- 定位符：{locator}\n"
            f"- 取数时间：{now}\n"
            f"- 口径：\n\n"
            "## 关键摘录\n\n> \n\n## 加工说明\n\n- \n"
        ),
        encoding="utf-8",
    )

    index_path = project / "search" / "index.json"
    index = load_json(index_path, {"sources": []}) or {"sources": []}
    index.setdefault("sources", []).append(
        {
            "id": source_id,
            "title": title,
            "grade": grade,
            "path": directory.name,
            "added": now[:10],
        }
    )
    save_json(index_path, index)

    log_path = project / "search" / "queries.jsonl"
    entry = {
        "ts": now,
        "tool": tool,
        "query": query,
        "locator": locator,
        "source": source_id,
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return directory


def add_sources_batch(project: Path | str, items: list[dict]) -> list[Path]:
    """按 JSON 列表批量建信封；每项字段与 add_source 参数一致。"""
    if not isinstance(items, list):
        raise ProjectError("批量来源必须是 JSON 数组，或 {\"sources\": [...]}")
    required = ["title", "tool", "locator", "publisher", "grade"]
    created: list[Path] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ProjectError(f"第 {index + 1} 项不是对象")
        missing = [key for key in required if not item.get(key)]
        if missing:
            raise ProjectError(f"第 {index + 1} 项缺少字段：{', '.join(missing)}")
        created.append(
            add_source(
                project,
                title=item["title"],
                tool=item["tool"],
                locator=item["locator"],
                publisher=item["publisher"],
                grade=item["grade"],
                query=item.get("query", ""),
                source_type=item.get("type", "web"),
                license_text=item.get("license", ""),
                notes=item.get("notes", ""),
                slug=item.get("slug"),
                extracted=item.get("extracted"),
            )
        )
    return created


def status_counts(project: Path | str) -> dict:
    project = Path(project)
    meta = load_json(project / "project.json", {}) or {}
    sources = []
    for child in (project / "search").iterdir() if (project / "search").is_dir() else []:
        meta_path = child / "meta.json"
        if child.is_dir() and meta_path.exists():
            try:
                sources.append(load_json(meta_path, {}) or {})
            except json.JSONDecodeError:
                continue
    claims = (load_json(project / "analysis/findings/claims.json", {}) or {}).get("claims", [])
    facts = (load_json(project / "analysis/findings/facts.json", {}) or {}).get("facts", [])
    conflicts = (load_json(project / "analysis/findings/conflicts.json", {}) or {}).get("conflicts", [])

    grades = {grade: 0 for grade in sorted(EVIDENCE_GRADES)}
    for source in sources:
        grade = source.get("evidence_grade")
        if grade in grades:
            grades[grade] += 1

    confidence = {"high": 0, "medium": 0, "low": 0}
    status = {"draft": 0, "active": 0, "superseded": 0, "retracted": 0}
    for claim in claims:
        if claim.get("confidence") in confidence:
            confidence[claim["confidence"]] += 1
        if claim.get("status") in status:
            status[claim["status"]] += 1

    return {
        "id": meta.get("id"),
        "title": meta.get("title"),
        "status": meta.get("status"),
        "sources": len(sources),
        "grades": grades,
        "claims": len(claims),
        "confidence": confidence,
        "claim_status": status,
        "facts": len(facts),
        "conflicts": len(conflicts),
        "conflicts_unresolved": sum(
            1 for item in conflicts if item.get("resolution") == "unresolved"
        ),
        "waivers": len(meta.get("gate_waivers", []) or []),
    }
