"""Research IR projection, validation and artifact snapshot support.

Research IR is a materialized, immutable candidate view for output pipelines.
The authoritative inputs remain the source index, research cycle, and finding
ledgers in the project. Builds copy their current state into one JSON payload
and record source hashes so downstream output can detect drift.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, date
from pathlib import Path

from .cycle import capture, cycle_status, digest, load_cycle
from .project import ProjectError, load_json, save_json

SCHEMA = "sa.research-ir/1"
REVISION_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")


def _load_optional(path: Path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ProjectError(f"无法读取 {path}: {exc}") from exc


def _project_relative(project: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError as exc:
        raise ProjectError(f"文件越出项目目录：{path}") from exc


def _hash_files(project: Path, paths: list[Path]) -> dict[str, str]:
    return {
        _project_relative(project, path): digest(path)
        for path in paths
        if path.is_file()
    }


def _load_sources(project: Path) -> dict[str, dict]:
    sources: dict[str, dict] = {}
    search = project / "search"
    if not search.is_dir():
        return sources
    for meta_path in sorted(search.glob("*/meta.json")):
        meta = _load_optional(meta_path, None)
        if not isinstance(meta, dict):
            continue
        source_id = meta.get("id")
        if not isinstance(source_id, str) or not source_id:
            continue
        if source_id in sources:
            raise ProjectError(f"来源 ID 重复：{source_id}")
        sources[source_id] = {
            "title": meta.get("title"),
            "publisher": meta.get("publisher"),
            "evidence_grade": meta.get("evidence_grade"),
            "source_type": meta.get("source_type"),
            "locator": meta.get("locator"),
            "published_at": meta.get("published_at"),
            "retrieved_at": meta.get("retrieved_at"),
            "path": _project_relative(project, meta_path),
            "sha256": digest(meta_path),
        }
    return sources


def _load_collection(project: Path, relative: str, key: str) -> list[dict]:
    data = _load_optional(project / relative, {key: []})
    values = data.get(key) if isinstance(data, dict) else None
    if not isinstance(values, list):
        raise ProjectError(f"{relative} 的 {key} 必须是数组")
    return values


def _cycle_projection(project: Path, agreement_id: str | None) -> tuple[dict, list[dict], list[dict], list[dict]]:
    ledger = project / "research/cycle.json"
    if not ledger.is_file():
        return {}, [], [], []
    cycle_data = load_cycle(project)
    records = cycle_data["records"]
    approved = [r for r in records if r.get("type") == "agreement" and r.get("status") == "approved"]
    current = approved[-1] if approved else None
    if agreement_id and current and current.get("id") != agreement_id:
        current = next((r for r in approved if r.get("id") == agreement_id), current)
    current_id = current.get("id") if current else None
    status = cycle_status(project)

    question_records = [
        r for r in records
        if r.get("type") == "question" and (current_id is None or r.get("agreement") == current_id)
    ]
    latest_answers: dict[str, dict] = {}
    for record in records:
        if record.get("type") == "answer":
            latest_answers[record["question"]] = record
    questions = []
    for question in question_records:
        answer = latest_answers.get(question["id"])
        questions.append({
            "id": question["id"],
            "text": question["text"],
            "status": answer.get("status") if answer else "unanswered",
            "round": answer.get("round") if answer else None,
            "summary": answer.get("summary") if answer else None,
            "limitations": list(answer.get("limitations", [])) if answer else [],
        })

    outcomes = {r.get("action") for r in records if r.get("type") == "outcome"}
    gaps = [
        {
            "id": action["id"],
            "question": action.get("question"),
            "reason": action["task"],
            "route": action["domain"],
            "acceptance": "登记 outcome 并关联冻结材料",
            "status": "open",
        }
        for action in records
        if action.get("type") == "action" and action.get("id") not in outcomes
    ]

    intent = {}
    if current:
        intent = {
            "agreement": current["id"],
            "question": current.get("question"),
            "purpose": current.get("purpose"),
            "audience": current.get("audience"),
            "scope": current.get("scope"),
            "out_of_scope": list(current.get("out_of_scope", [])),
            "acceptance": list(current.get("acceptance", [])),
            "as_of": current.get("as_of"),
            "approval": current.get("approval"),
        }
    return {"status": status, "record_count": len(records)}, questions, gaps, [intent] if intent else []


def build_research_ir(
    project: Path | str,
    *,
    revision: str = "current",
    agreement_id: str | None = None,
) -> dict:
    project = Path(project).resolve()
    if not REVISION_RE.fullmatch(revision):
        raise ProjectError("Research IR revision 只能使用小写字母、数字和连字符")
    meta = _load_optional(project / "project.json", None)
    if not isinstance(meta, dict) or not meta.get("id"):
        raise ProjectError("不是有效项目目录：缺少 project.json")

    claims = _load_collection(project, "analysis/findings/claims.json", "claims")
    facts = _load_collection(project, "analysis/findings/facts.json", "facts")
    conflicts = _load_collection(project, "analysis/findings/conflicts.json", "conflicts")
    sources = _load_sources(project)
    process, questions, gaps, intents = _cycle_projection(project, agreement_id)

    if intents:
        intent = intents[0]
    else:
        intent = {
            "agreement": agreement_id,
            "question": meta.get("question"),
            "purpose": None,
            "audience": meta.get("requester") or None,
            "scope": None,
            "out_of_scope": list(meta.get("out_of_scope", [])),
            "acceptance": list(meta.get("acceptance", [])),
            "as_of": meta.get("as_of"),
            "approval": None,
        }

    document_path = project / "report/document.json"
    document = _load_optional(document_path, None)
    narrative = None
    if isinstance(document, dict):
        narrative = {
            "path": _project_relative(project, document_path),
            "sha256": digest(document_path),
            "document": document,
        }

    tracked_files = [
        project / "analysis/findings/claims.json",
        project / "analysis/findings/facts.json",
        project / "analysis/findings/conflicts.json",
        document_path,
    ]
    return {
        "schema": SCHEMA,
        "project": meta["id"],
        "revision": revision,
        "as_of": meta.get("as_of"),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generator": {"name": "sa", "module": "research_ir", "version": 1},
        "intent": intent,
        "process": process,
        "questions": questions,
        "evidence_index": sources,
        "assertions": {
            "claims": claims,
            "facts": facts,
            "conflicts": conflicts,
        },
        "syntheses": [],
        "relations": [],
        "narrative": narrative,
        "gaps": gaps,
        "boundaries": list(intent.get("out_of_scope", [])),
        "source_hashes": _hash_files(project, tracked_files),
    }


def _ids(items: list[dict], field: str = "id") -> set[str]:
    values = [item.get(field) for item in items if isinstance(item, dict)]
    return {value for value in values if isinstance(value, str) and value}


def validate_research_ir(
    project: Path | str,
    data: dict,
    *,
    verify_sources: bool = True,
) -> list[str]:
    project = Path(project).resolve()
    errors: list[str] = []
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return ["未知 Research IR schema"]
    meta = _load_optional(project / "project.json", {})
    if data.get("project") != meta.get("id"):
        errors.append("Research IR project 与 project.json 不一致")
    if not isinstance(data.get("revision"), str) or not REVISION_RE.fullmatch(data["revision"]):
        errors.append("Research IR revision 非法")
    try:
        date.fromisoformat(str(data.get("as_of", "")))
    except ValueError:
        errors.append("Research IR as_of 必须是 ISO 日期")

    intent = data.get("intent")
    if not isinstance(intent, dict):
        errors.append("intent 必须是对象")
        intent = {}
    ledger = project / "research/cycle.json"
    if ledger.is_file():
        try:
            records = load_cycle(project)["records"]
        except ProjectError as exc:
            errors.append(f"研究循环无法读取：{exc}")
        else:
            approved = {
                record["id"] for record in records
                if record.get("type") == "agreement" and record.get("status") == "approved"
            }
            agreement = intent.get("agreement")
            if agreement and agreement not in approved:
                errors.append(f"intent.agreement 不是已批准约定：{agreement}")

    question_ids = [
        question.get("id")
        for question in data.get("questions", []) or []
        if isinstance(question, dict)
    ]
    if len(question_ids) != len(set(question_ids)):
        errors.append("questions 存在重复 ID")
    if any(not isinstance(value, str) or not value for value in question_ids):
        errors.append("questions 条目缺少 ID")

    evidence = data.get("evidence_index")
    if not isinstance(evidence, dict):
        errors.append("evidence_index 必须是对象")
        evidence = {}
    evidence_ids = set(evidence)
    if verify_sources:
        for source_id, source in evidence.items():
            if not isinstance(source, dict):
                errors.append(f"evidence_index.{source_id} 必须是对象")
                continue
            relative = source.get("path")
            expected = source.get("sha256")
            if not isinstance(relative, str) or not isinstance(expected, str):
                errors.append(f"evidence_index.{source_id} 缺少 path/sha256")
                continue
            path = (project / relative).resolve()
            if not path.is_relative_to(project) or not path.is_file():
                errors.append(f"evidence_index.{source_id} 文件不存在或越出项目")
            elif digest(path) != expected:
                errors.append(f"evidence_index.{source_id} 哈希不一致")
            else:
                meta_data = _load_optional(path, {})
                if isinstance(meta_data, dict) and meta_data.get("id") != source_id:
                    errors.append(f"evidence_index.{source_id} 与来源 meta.id 不一致")

    assertions = data.get("assertions")
    if not isinstance(assertions, dict):
        errors.append("assertions 必须是对象")
        assertions = {}
    claims = assertions.get("claims", [])
    facts = assertions.get("facts", [])
    conflicts = assertions.get("conflicts", [])
    for name, items in (("claims", claims), ("facts", facts), ("conflicts", conflicts)):
        if not isinstance(items, list):
            errors.append(f"assertions.{name} 必须是数组")
            continue
        ids = [item.get("id") for item in items if isinstance(item, dict)]
        if len(ids) != len(set(ids)):
            errors.append(f"assertions.{name} 存在重复 ID")
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                errors.append(f"assertions.{name} 条目缺少 ID")
    claim_ids = _ids(claims) if isinstance(claims, list) else set()
    fact_ids = _ids(facts) if isinstance(facts, list) else set()
    conflict_ids = _ids(conflicts) if isinstance(conflicts, list) else set()
    for claim in claims if isinstance(claims, list) else []:
        if not isinstance(claim, dict):
            continue
        for source_id in claim.get("evidence", []) or []:
            if source_id not in evidence_ids:
                errors.append(f"{claim.get('id')} 引用不存在来源 {source_id}")
        for conflict_id in claim.get("conflicts", []) or []:
            if conflict_id not in conflict_ids:
                errors.append(f"{claim.get('id')} 引用不存在冲突 {conflict_id}")
    for fact in facts if isinstance(facts, list) else []:
        if not isinstance(fact, dict):
            continue
        for source_id in fact.get("evidence", []) or []:
            if source_id not in evidence_ids:
                errors.append(f"{fact.get('id')} 引用不存在来源 {source_id}")
    for conflict in conflicts if isinstance(conflicts, list) else []:
        if not isinstance(conflict, dict):
            continue
        for position in conflict.get("positions", []) or []:
            source_id = position.get("evidence") if isinstance(position, dict) else None
            if source_id not in evidence_ids:
                errors.append(f"{conflict.get('id')} 引用不存在来源 {source_id}")

    for synthesis in data.get("syntheses", []) or []:
        if not isinstance(synthesis, dict):
            errors.append("syntheses 条目必须是对象")
            continue
        for field, allowed in (
            ("claim_ids", claim_ids),
            ("fact_ids", fact_ids),
            ("conflict_ids", conflict_ids),
            ("evidence_ids", evidence_ids),
        ):
            for reference in synthesis.get(field, []) or []:
                if reference not in allowed:
                    errors.append(f"{synthesis.get('id')} 的 {field} 引用不存在：{reference}")

    narrative = data.get("narrative")
    if narrative is not None:
        if not isinstance(narrative, dict):
            errors.append("narrative 必须是对象或 null")
        else:
            relative = narrative.get("path")
            expected = narrative.get("sha256")
            embedded = narrative.get("document")
            if not isinstance(relative, str) or not isinstance(expected, str):
                errors.append("narrative 缺少 path/sha256")
            else:
                path = (project / relative).resolve()
                if not path.is_relative_to(project) or not path.is_file():
                    errors.append("narrative 文件不存在或越出项目")
                elif digest(path) != expected:
                    errors.append("narrative 哈希不一致")
                elif not isinstance(embedded, dict):
                    errors.append("narrative.document 必须是对象")
                elif _load_optional(path, None) != embedded:
                    errors.append("narrative.document 与当前文档模型不一致")

    if verify_sources:
        for relative, expected in (data.get("source_hashes") or {}).items():
            # cycle.json changes when the snapshot itself is captured. Intent and
            # questions are already materialized above, so the process ledger is
            # not treated as a stable content input.
            if relative == "research/cycle.json":
                continue
            path = (project / relative).resolve()
            if not path.is_relative_to(project) or not path.is_file():
                errors.append(f"source_hashes 文件不存在或越出项目：{relative}")
            elif digest(path) != expected:
                errors.append(f"source_hashes 哈希不一致：{relative}")
    return errors


def write_research_ir(
    project: Path | str,
    data: dict,
    *,
    output: Path | str | None = None,
) -> Path:
    project = Path(project).resolve()
    target = Path(output) if output else project / "analysis/research-ir/current.json"
    if not target.is_absolute():
        target = project / target
    target = target.resolve()
    if not target.is_relative_to(project):
        raise ProjectError("Research IR 输出必须位于项目目录")
    errors = validate_research_ir(project, data)
    if errors:
        raise ProjectError("\n".join(errors))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def snapshot_research_ir(
    project: Path | str,
    *,
    revision: str = "current",
    artifact_id: str | None = None,
    label: str | None = None,
) -> str:
    project = Path(project).resolve()
    data = build_research_ir(project, revision=revision)
    relative = Path("analysis/research-ir") / f"{revision}.json"
    write_research_ir(project, data, output=relative)
    artifact_id = artifact_id or f"a-ir-{revision}"
    return capture(
        project,
        relative.as_posix(),
        artifact_id,
        label or f"Research IR snapshot {revision}",
    )

