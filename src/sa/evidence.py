"""证据台账校验（sa lint 的核心）。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .project import (
    EVIDENCE_GRADES,
    PROJECT_ID_RE,
    REQUIRED_DIRS,
    load_json,
)

REQUIRED_META = [
    "id", "title", "source_type", "tool", "locator",
    "publisher", "retrieved_at", "evidence_grade",
]
REQUIRED_PROJECT = ["id", "title", "status", "created", "as_of"]
CONFIDENCE = {"high", "medium", "low"}
CLAIM_STATUS = {"draft", "active", "superseded", "retracted"}
RESOLUTIONS = {"explained", "unresolved"}
SOURCE_DIR_RE = re.compile(r"^(s-\d{4})-")
CITATION_RE = re.compile(r"\[\^((?:s|c|f|x)-\d{4})\]")
STATUS_LINE_RE = re.compile(r"状态[：:]\s*([a-zA-Z_-]+)")
GATES = {"G0", "G1", "G2", "G3"}
GATE_MARK_RE = re.compile(r"\|\s*(G[0-3])\s*\|\s*(🟢|🟡|⚪)")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.infos: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def info(self, message: str) -> None:
        self.infos.append(message)

    @property
    def ok(self) -> bool:
        return not self.errors


def _parse_time(value: str):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def _unique_ids(items: list[dict], kind: str, report: Report) -> set[str]:
    seen: set[str] = set()
    for index, item in enumerate(items):
        item_id = item.get("id")
        if not item_id:
            report.error(f"{kind}[{index}] 缺少 id")
            continue
        if item_id in seen:
            report.error(f"{kind} id 重复：{item_id}")
        seen.add(item_id)
    return seen


def _load_collection(project: Path, rel: str, key: str, report: Report) -> list[dict]:
    path = project / rel
    if not path.exists():
        report.error(f"缺少文件：{rel}")
        return []
    try:
        data = load_json(path, {}) or {}
    except json.JSONDecodeError as exc:
        report.error(f"{rel} 不是合法 JSON：{exc}")
        return []
    items = data.get(key)
    if not isinstance(items, list):
        report.error(f"{rel} 缺少数组字段 '{key}'")
        return []
    return items


def lint_project(
    project: Path | str,
    stale_days: int | None = None,
    report_path: Path | str | None = None,
) -> Report:
    project = Path(project)
    report = Report()

    if not project.is_dir():
        report.error(f"项目目录不存在：{project}")
        return report

    meta_path = project / "project.json"
    if not meta_path.exists():
        report.error("缺少 project.json")
        return report
    try:
        project_meta = load_json(meta_path, {}) or {}
    except json.JSONDecodeError as exc:
        report.error(f"project.json 不是合法 JSON：{exc}")
        return report

    for key in REQUIRED_PROJECT:
        if not project_meta.get(key):
            report.error(f"project.json 缺少必填字段：{key}")
    project_id = project_meta.get("id", "")
    if project_id and not PROJECT_ID_RE.match(project_id):
        report.error(f"项目 id 格式错误：{project_id}（应为 p-YYYYMMDD-slug）")

    workflow = project_meta.get("workflow", "legacy")
    if not isinstance(workflow, str) or workflow not in {"legacy", "sa.research/1"}:
        report.error("未知 workflow；不能静默按旧契约解释")
    native_cycle = workflow == "sa.research/1"
    if native_cycle and project_meta.get("status") not in ("active", "suspended", "archived"):
        report.error("新研究项目生命周期只能 active/suspended/archived；交付与轮次单独记录")
    if native_cycle or (project / "research/cycle.json").exists():
        from .cycle import read_json, validate
        from .project import ProjectError
        try:
            for error in validate(project, read_json(project / "research/cycle.json")):
                report.error("research: " + error)
        except ProjectError as exc:
            report.error(str(exc))
    for rel in REQUIRED_DIRS:
        if native_cycle and rel == "_dev":
            continue
        if not (project / rel).is_dir():
            report.error(f"缺少目录：{rel}")

    # 状态一致性：project.json ↔ _dev/03
    state_file = project / "_dev" / "03-调研状态.md"
    state_text = state_file.read_text(encoding="utf-8") if state_file.exists() else ""
    if state_file.exists() and not native_cycle:
        match = STATUS_LINE_RE.search(state_text)
        if not match:
            report.warn("_dev/03-调研状态.md 未找到「状态：<status>」行")
        elif project_meta.get("status") and match.group(1) != project_meta["status"]:
            report.error(
                "状态不一致：project.json="
                f"{project_meta['status']}，_dev/03={match.group(1)}"
            )

    # Gate waiver
    waivers = [] if native_cycle else project_meta.get("gate_waivers", [])
    if waivers and not isinstance(waivers, list):
        report.error("gate_waivers 必须是数组")
        waivers = []
    gate_marks = dict(GATE_MARK_RE.findall(state_text))
    for index, waiver in enumerate(waivers):
        if not isinstance(waiver, dict):
            report.error(f"gate_waivers[{index}] 不是对象")
            continue
        gate = waiver.get("gate")
        if gate not in GATES:
            report.error(f"gate_waivers[{index}] gate 非法：{gate}")
            continue
        for key in ("reason", "date", "approved_by"):
            if not waiver.get(key):
                report.error(f"gate_waivers[{index}] 缺少字段：{key}")
        if gate not in gate_marks:
            report.warn(f"{gate} waiver 未在 _dev/03 门禁表中找到对应行")
        elif gate_marks[gate] == "🟢":
            report.warn(f"{gate} 已标绿但仍有 waiver，应删除豁免")
        elif gate_marks[gate] == "🟡":
            report.info(f"{gate} 条件性通过（waiver）：{waiver.get('reason')}")

    # 来源
    sources: dict[str, dict] = {}
    search_dir = project / "search"
    if search_dir.is_dir():
        for child in sorted(search_dir.iterdir()):
            if not child.is_dir() or not SOURCE_DIR_RE.match(child.name):
                continue
            meta_file = child / "meta.json"
            if not meta_file.exists():
                report.error(f"来源目录缺少 meta.json：{child.name}")
                continue
            try:
                source = load_json(meta_file, {}) or {}
            except json.JSONDecodeError as exc:
                report.error(f"{child.name}/meta.json 不是合法 JSON：{exc}")
                continue
            source_id = source.get("id", "")
            if not source_id:
                report.error(f"{child.name}/meta.json 缺少 id")
                continue
            if source_id in sources:
                report.error(f"来源 id 重复：{source_id}")
                continue
            sources[source_id] = source
            dir_id = SOURCE_DIR_RE.match(child.name).group(1)
            if dir_id != source_id:
                report.error(f"目录名与 id 不一致：{child.name} vs {source_id}")
            for key in REQUIRED_META:
                if source.get(key) in (None, ""):
                    report.error(f"{source_id} 缺少必填字段：{key}")
            grade = source.get("evidence_grade")
            if grade not in EVIDENCE_GRADES:
                report.error(f"{source_id} evidence_grade 非法：{grade}")
            retrieved = _parse_time(source.get("retrieved_at"))
            if retrieved is None:
                report.error(f"{source_id} retrieved_at 不是合法时间")
            else:
                limit = stale_days or project_meta.get("stale_days", 180)
                age = (datetime.now().astimezone() - retrieved).days
                if age > int(limit):
                    report.warn(f"{source_id} 已 {age} 天未复核（阈值 {limit} 天）")

    # index.json 一致性
    index = load_json(search_dir / "index.json", {"sources": []}) if search_dir.is_dir() else {}
    indexed = {item.get("id") for item in (index or {}).get("sources", []) if isinstance(item, dict)}
    for source_id in sources:
        if source_id not in indexed:
            report.warn(f"{source_id} 未登记到 search/index.json")
    for source_id in indexed - set(sources):
        report.error(f"index.json 登记了不存在的来源：{source_id}")

    # claims
    claims = _load_collection(project, "analysis/findings/claims.json", "claims", report)
    claim_ids = _unique_ids(claims, "claim", report)
    used_sources: set[str] = set()
    for claim in claims:
        claim_id = claim.get("id", "<unknown>")
        if not isinstance(claim.get("statement"), str) or not claim["statement"].strip():
            report.error(f"{claim_id} 缺少 statement")
        confidence = claim.get("confidence")
        if confidence not in CONFIDENCE:
            report.error(f"{claim_id} confidence 非法：{confidence}")
        status = claim.get("status")
        if status not in CLAIM_STATUS:
            report.error(f"{claim_id} status 非法：{status}")
        if not claim.get("scope"):
            report.warn(f"{claim_id} 未写 scope（适用边界）")
        evidence = claim.get("evidence")
        if not isinstance(evidence, list):
            report.error(f"{claim_id} evidence 必须是数组")
            evidence = []
        if confidence in {"high", "medium"} and not evidence:
            report.error(f"{claim_id} 置信度为 {confidence} 但无证据")
        for source_id in evidence:
            used_sources.add(source_id)
            if source_id not in sources:
                report.error(f"{claim_id} 引用了不存在的来源：{source_id}")
            elif sources[source_id].get("evidence_grade") == "E4":
                report.warn(f"{claim_id} 直接把 E4 线索当证据：{source_id}")
        if "counter_evidence" not in claim:
            report.warn(f"{claim_id} 缺少 counter_evidence（查过则写 []）")
        for conflict_id in claim.get("conflicts", []) or []:
            if not isinstance(conflict_id, str) or not conflict_id.startswith("x-"):
                report.warn(f"{claim_id} 的 conflicts 含非冲突 id：{conflict_id}")

    # facts
    facts = _load_collection(project, "analysis/findings/facts.json", "facts", report)
    _unique_ids(facts, "fact", report)
    for fact in facts:
        fact_id = fact.get("id", "<unknown>")
        for key in ("metric", "value", "unit", "period", "as_of", "evidence"):
            if fact.get(key) in (None, "", []):
                report.error(f"{fact_id} 缺少必填字段：{key}")
        for source_id in fact.get("evidence", []) or []:
            used_sources.add(source_id)
            if source_id not in sources:
                report.error(f"{fact_id} 引用了不存在的来源：{source_id}")

    # conflicts
    conflicts = _load_collection(project, "analysis/findings/conflicts.json", "conflicts", report)
    conflict_ids = _unique_ids(conflicts, "conflict", report)
    for conflict in conflicts:
        conflict_id = conflict.get("id", "<unknown>")
        resolution = conflict.get("resolution")
        if resolution not in RESOLUTIONS and not str(resolution).startswith("preferred:"):
            report.error(f"{conflict_id} resolution 非法：{resolution}")
        positions = conflict.get("positions")
        if not isinstance(positions, list) or len(positions) < 2:
            report.error(f"{conflict_id} 至少需要两个 positions")
            continue
        for position in positions:
            source_id = position.get("evidence")
            used_sources.add(source_id)
            if source_id not in sources:
                report.error(f"{conflict_id} 引用了不存在的来源：{source_id}")
        if resolution != "unresolved" and not conflict.get("rationale"):
            report.warn(f"{conflict_id} 已处置但未写 rationale")

    for claim in claims:
        for conflict_id in claim.get("conflicts", []) or []:
            if conflict_id not in conflict_ids:
                report.error(f"{claim.get('id')} 引用了不存在的冲突：{conflict_id}")

    # 孤儿来源
    for source_id in sources:
        if source_id not in used_sources:
            report.info(f"{source_id} 尚未被任何 claim/fact/conflict 引用")

    # 报告引用
    if report_path:
        claims_by_id = {claim.get("id"): claim for claim in claims if claim.get("id")}
        facts_by_id = {fact.get("id"): fact for fact in facts if fact.get("id")}
        kind = _lint_report(
            Path(report_path),
            sources,
            claims_by_id,
            facts_by_id,
            conflict_ids,
            used_sources,
            report,
        )
        if kind:
            report.info(kind)

    return report


def _lint_report(
    path: Path,
    sources: dict[str, dict],
    claims: dict[str, dict],
    facts: dict[str, dict],
    conflict_ids: set[str],
    used_sources: set[str],
    report: Report,
) -> str | None:
    if not path.exists():
        report.error(f"报告不存在：{path}")
        return None
    text = path.read_text(encoding="utf-8")
    citations = set(CITATION_RE.findall(text))
    if not citations:
        report.warn("报告中没有任何 [^s-xxxx] / [^f-xxxx] 引用")
    for ref in citations:
        if ref.startswith("s-"):
            if ref not in sources:
                report.error(f"报告引用了不存在的来源：{ref}")
            elif ref not in used_sources:
                report.warn(f"报告引用的来源未被任何 claim/fact/conflict 使用：{ref}")
        elif ref.startswith("c-"):
            claim = claims.get(ref)
            if claim is None:
                report.error(f"报告引用了不存在的结论：{ref}")
            elif claim.get("status") != "active":
                report.error(
                    f"报告引用了非 active 结论：{ref}（status={claim.get('status')}）"
                )
        elif ref.startswith("f-"):
            if ref not in facts:
                report.error(f"报告引用了不存在的基准事实：{ref}")
        elif ref.startswith("x-"):
            if ref not in conflict_ids:
                report.error(f"报告引用了不存在的冲突：{ref}")

    cited_claims = {ref for ref in citations if ref.startswith("c-")}
    for claim_id, claim in claims.items():
        if (
            claim.get("status") == "active"
            and claim.get("confidence") == "high"
            and claim_id not in cited_claims
        ):
            report.info(f"高置信度结论 {claim_id} 未在报告中直接引用（背景结论可忽略）")
    return f"报告引用 {len(citations)} 条"
