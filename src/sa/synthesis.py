"""Synthesis review/design ledgers, baselines and frozen snapshots."""
from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from .project import ProjectError, load_json, save_json


SCHEMA = "sa.synthesis/1"
WORK_MODEL_SCHEMA = "sa.work-model/1"
SNAPSHOT_SCHEMA = "sa.work-snapshot/1"
ITEM_STATUS = {"planned", "active", "blocked", "done", "unknown"}
CONTENT_LAYERS = {"user_statement", "material", "inference", "unknown"}
RECORD_TYPES = {
    "round",
    "review",
    "question",
    "answer",
    "correction",
    "design_proposal",
    "design_decision",
    "design_artifact",
    "advisory_panel",
    "specialist_task",
    "alignment",
    "snapshot",
    "decision",
}
QUESTION_PRIORITIES = {"high", "medium", "low"}
ANSWER_STATUSES = {"answered", "unknown", "skipped", "deferred"}
ALIGNMENT_STATUSES = {
    "confirmed",
    "disputed",
    "unknown",
    "deferred",
    "out_of_scope",
    "accepted",
    "rejected",
    "superseded",
}
ROUND_DECISIONS = {"exit", "continue", "drill_down", "park"}
ROUND_PROCESSES = {"review", "design", "mixed"}
BASELINE_KINDS = {"knowledge", "design", "mixed"}
DESIGN_DECISIONS = {"accepted", "rejected", "deferred"}
DESIGN_ARTIFACT_KINDS = {
    "model",
    "schema",
    "interface",
    "workflow",
    "research-design",
    "experiment",
    "narrative",
    "other",
}
ADVISORY_MODES = {"replicate", "heterogeneous"}
ADVISORY_STATUSES = {"completed", "partial", "failed"}
SPECIALIST_STATUSES = {"completed", "partial", "failed", "blocked"}
ROLE_IDS = {
    "principal",
    "research_assistant",
    "assistant_researcher",
    "research_advisor",
    "research_specialist",
}
CONTENT_NATURES = {
    "observation",
    "interpretation",
    "goal",
    "constraint",
    "assumption",
    "proposal",
    "option",
    "decision",
    "plan",
    "unknown",
}
LIFECYCLE_STATUSES = {"proposed", "accepted", "rejected", "deferred", "superseded"}
PROPOSER_ROLES = {"principal", "assistant_researcher", "research_advisor", "research_specialist"}
REQUESTER_ROLES = {"principal", "research_assistant", "assistant_researcher"}
DESIGN_RECORD_TYPES = {
    "design_proposal",
    "design_decision",
    "design_artifact",
    "advisory_panel",
    "specialist_task",
}
ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,79}$")
LAYER_LABELS = {
    "user_statement": "首席研究员陈述",
    "material": "材料记录",
    "inference": "代理归纳",
    "unknown": "未知",
}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text() -> re.Pattern[str]:
    return re.compile(r"^[0-9a-f]{64}$")


def _project_file(project: Path, value: str) -> tuple[Path | None, str | None]:
    if not isinstance(value, str) or not value.strip():
        return None, "路径必须是非空文本"
    relative = Path(value)
    if relative.is_absolute():
        return None, "路径必须是工作区相对路径"
    path = (project / relative).resolve()
    if not path.is_relative_to(project):
        return None, "路径越出工作区"
    if not path.is_file():
        return None, "文件不存在"
    return path, None


def _model_digest(model: dict) -> str:
    payload = json.dumps(
        model,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _digest_bytes(payload)


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
        "不从研究循环推断状态。\n\n"
        "复盘、设计和循环事件通过 `sa synthesis apply --file <records.json>` 追加；"
        "关闭轮次后使用 `sa synthesis snapshot` 冻结 knowledge/design baseline，"
        "正式呈现使用 `sa synthesis build --snapshot <id>`。\n",
        encoding="utf-8",
    )
    (project / "work-model/README.md").write_text(
        "# 工作模型\n\n"
        "保存从首席研究员材料归一化得到的工作主题、进展、结果、阻塞、依赖和未知项。"
        "代理归纳必须能回指 `brief/provided/` 中的材料。\n\n"
        "这里是一轮轮复盘迭代后的当前知识态；设计提案、决定和研究过程记录保存在 "
        "`synthesis/ledger.json`。正式输出应绑定 "
        "`synthesis/snapshots/<id>/snapshot.json`，而不是直接读取本文件。\n",
        encoding="utf-8",
    )
    return path


def _known_material_ids(project: Path) -> set[str]:
    provided = load_json(project / "brief/provided/manifest.json", {}) or {}
    references = load_json(project / "references/index.json", {}) or {}
    known = {
        item.get("id")
        for item in provided.get("items", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    known.update(
        item.get("id")
        for item in references.get("references", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    )
    return known


def _validate_work_model(project: Path, model: dict, meta: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(model, dict) or model.get("schema") != WORK_MODEL_SCHEMA:
        return [f"work model schema 必须是 {WORK_MODEL_SCHEMA}"]
    if model.get("project") != meta.get("id"):
        errors.append("work model project 与 project.json 不一致")
    try:
        date.fromisoformat(str(model.get("as_of", "")))
    except ValueError:
        errors.append("work model as_of 必须是 ISO 日期")
    if not isinstance(model.get("audience"), str):
        errors.append("work model audience 必须是文本")
    if not isinstance(model.get("period"), dict):
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
    known_materials = _known_material_ids(project)
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
                if value.get("nature") is not None and value.get("nature") not in CONTENT_NATURES:
                    errors.append(f"{entry_mark}.nature 非法")
                if value.get("actor_role") is not None and value.get("actor_role") not in ROLE_IDS:
                    errors.append(f"{entry_mark}.actor_role 非法")
                if (
                    value.get("lifecycle") is not None
                    and value.get("lifecycle") not in LIFECYCLE_STATUSES
                ):
                    errors.append(f"{entry_mark}.lifecycle 非法")
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


def _validate_records(
    project: Path,
    records: list,
    known_materials: set[str],
    work_items: set[str],
) -> list[str]:
    errors: list[str] = []
    seen: dict[str, dict] = {}
    rounds: dict[str, dict] = {}
    closed: set[str] = set()
    reviews: dict[str, int] = {}
    questions: dict[str, dict] = {}
    answers: dict[str, str] = {}
    aligned: set[str] = set()
    alignment_hashes: dict[str, str] = {}
    decision_rounds: set[str] = set()
    snapshot_rounds: dict[str, str] = {}
    round_topics: dict[str, str] = {}
    topics: set[str] = set()
    design_proposals: dict[str, dict] = {}
    design_decisions: dict[str, dict] = {}
    design_artifacts: dict[str, dict] = {}
    advisory_panels: dict[str, dict] = {}
    specialist_tasks: dict[str, dict] = {}

    def text(record: dict, field: str, mark: str) -> bool:
        if not isinstance(record.get(field), str) or not record[field].strip():
            errors.append(f"{mark}.{field} 必须是非空文本")
            return False
        return True

    def values(record: dict, field: str, mark: str, *, required: bool = False) -> list | None:
        value = record.get(field)
        if value is None and not required:
            return []
        if not isinstance(value, list) or any(
            not isinstance(entry, str) or not entry.strip() for entry in value
        ):
            errors.append(f"{mark}.{field} 必须是文本数组")
            return None
        if required and not value:
            errors.append(f"{mark}.{field} 不可为空")
            return None
        return value

    def role(
        record: dict,
        field: str,
        mark: str,
        allowed: set[str],
        *,
        required: bool = True,
    ) -> str | None:
        value = record.get(field)
        if value is None and not required:
            return None
        if value not in allowed:
            errors.append(f"{mark}.{field} 必须是 {', '.join(sorted(allowed))} 之一")
            return None
        return value

    for index, record in enumerate(records):
        mark = f"synthesis.records[{index}]"
        if not isinstance(record, dict):
            errors.append(mark + " 必须是对象")
            continue
        record_id = record.get("id")
        kind = record.get("type")
        if not isinstance(record_id, str) or not ID_RE.fullmatch(record_id) or record_id in seen:
            errors.append(mark + ".id 非法或重复")
            continue
        mark = record_id
        if kind not in RECORD_TYPES:
            errors.append(mark + ".type 非法")
            continue
        try:
            timestamp = datetime.fromisoformat(record.get("at", ""))
            if timestamp.tzinfo is None:
                raise ValueError()
        except (TypeError, ValueError):
            errors.append(mark + ".at 必须是带时区 ISO 时间")

        def round_ref() -> dict:
            value = record.get("round")
            target = rounds.get(value)
            if not target:
                errors.append(f"{mark}.round 必须引用前序 round")
                return {}
            return target

        if kind == "round":
            text(record, "goal", mark)
            if record.get("process") is not None and record.get("process") not in ROUND_PROCESSES:
                errors.append(mark + ".process 必须是 review、design 或 mixed")
            topic_fields = {"topic", "topic_title", "related_work_items"}
            if topic_fields.intersection(record):
                if not isinstance(record.get("topic"), str) or not ID_RE.fullmatch(record["topic"]):
                    errors.append(mark + ".topic 必须是小写 ID")
                text(record, "topic_title", mark)
                related = values(record, "related_work_items", mark)
                if related is not None:
                    for item_id in related:
                        if item_id not in work_items:
                            errors.append(
                                f"{mark}.related_work_items 引用了不存在的工作主题：{item_id}"
                            )
                if record.get("topic") in topics and "parent_snapshot" not in record:
                    errors.append(mark + " 同一主题续轮必须引用前序 parent_snapshot")
            parent_snapshot = record.get("parent_snapshot")
            parent_topic = record.get("parent_topic")
            if parent_snapshot is not None or parent_topic is not None:
                if not isinstance(parent_snapshot, str) or not parent_snapshot.strip():
                    errors.append(mark + ".parent_snapshot 必须是非空引用")
                elif parent_snapshot not in snapshot_rounds:
                    errors.append(mark + ".parent_snapshot 必须引用前序 snapshot")
                if parent_topic is not None:
                    if not isinstance(parent_topic, str) or not ID_RE.fullmatch(parent_topic):
                        errors.append(mark + ".parent_topic 必须是小写 ID")
                    elif parent_topic not in topics:
                        errors.append(mark + ".parent_topic 必须引用前序 topic")
                    elif isinstance(parent_snapshot, str):
                        parent_round_id = snapshot_rounds.get(parent_snapshot)
                        if round_topics.get(parent_round_id) != parent_topic:
                            errors.append(mark + ".parent_topic 与 parent_snapshot 不一致")
                if isinstance(parent_snapshot, str):
                    parent_round_id = snapshot_rounds.get(parent_snapshot)
                    parent_decision = next(
                        (
                            decision for decision in records[:index]
                            if decision.get("type") == "decision"
                            and decision.get("round") == parent_round_id
                        ),
                        None,
                    )
                    if not parent_decision:
                        errors.append(mark + " 父轮次缺少首席研究员循环出口决定")
                    elif parent_decision.get("decision") == "drill_down":
                        if parent_decision.get("target_topic") != record.get("topic"):
                            errors.append(mark + " 父轮次 drill_down 目标与当前 topic 不一致")
                    elif parent_decision.get("decision") == "continue":
                        parent_topic_of_round = round_topics.get(parent_round_id)
                        if parent_topic_of_round and record.get("topic") != parent_topic_of_round:
                            errors.append(mark + " 同主题续轮必须沿用父轮次 topic")
                    else:
                        errors.append(mark + " 父轮次的循环出口不允许创建新轮次")
        elif kind == "review":
            target = round_ref()
            if target and target["id"] in closed:
                errors.append(mark + " 不能写入已关闭轮次")
            text(record, "summary", mark)
            changes = values(record, "changes", mark)
            if changes is not None:
                for item_id in changes:
                    if item_id not in work_items:
                        errors.append(f"{mark}.changes 引用了不存在的工作主题：{item_id}")
            gaps = values(record, "gaps", mark)
            del gaps
            materials = values(record, "materials", mark, required=True)
            if materials is not None:
                for material in materials:
                    if material not in known_materials:
                        errors.append(f"{mark}.materials 引用了不存在的材料：{material}")
            if target:
                reviews[record["round"]] = reviews.get(record["round"], 0) + 1
            if not isinstance(record.get("model_sha256"), str) or not re.fullmatch(
                r"[0-9a-f]{64}", record["model_sha256"]
            ):
                errors.append(mark + ".model_sha256 必须是模型摘要")
        elif kind == "question":
            target = round_ref()
            if target and target["id"] in closed:
                errors.append(mark + " 不能写入已关闭轮次")
            text(record, "text", mark)
            if record.get("priority") not in QUESTION_PRIORITIES:
                errors.append(f"{mark}.priority 非法")
            text(record, "why", mark)
            if target:
                questions[record_id] = record
        elif kind == "answer":
            target = round_ref()
            if target and target["id"] in closed:
                errors.append(mark + " 不能写入已关闭轮次")
            question_id = record.get("question")
            question = questions.get(question_id)
            if not question or question.get("round") != record.get("round"):
                errors.append(f"{mark}.question 必须引用本轮前序问题")
            elif question_id in answers:
                errors.append(f"{mark}.question 已作答；修订请新建轮次")
            if record.get("status") not in ANSWER_STATUSES:
                errors.append(f"{mark}.status 非法")
            text(record, "summary", mark)
            materials = values(record, "materials", mark) or []
            for material in materials:
                if material not in known_materials:
                    errors.append(f"{mark}.materials 引用了不存在的材料：{material}")
            if question and question_id not in answers:
                answers[question_id] = record_id
        elif kind == "correction":
            target = round_ref()
            if target and target["id"] in closed:
                errors.append(mark + " 不能写入已关闭轮次")
            text(record, "target", mark)
            text(record, "summary", mark)
            target_value = record.get("target")
            if isinstance(target_value, str) and target_value.startswith("w-") and target_value not in work_items:
                errors.append(f"{mark}.target 引用了不存在的工作主题：{target_value}")
            materials = values(record, "materials", mark) or []
            for material in materials:
                if material not in known_materials:
                    errors.append(f"{mark}.materials 引用了不存在的材料：{material}")
            if not isinstance(record.get("model_sha256"), str) or not re.fullmatch(
                r"[0-9a-f]{64}", record["model_sha256"]
            ):
                errors.append(mark + ".model_sha256 必须是模型摘要")
        elif kind == "design_proposal":
            target = round_ref()
            if target and target["id"] in closed:
                errors.append(mark + " 不能写入已关闭轮次")
            role(record, "proposed_by", mark, PROPOSER_ROLES)
            for field in ("title", "problem", "recommendation"):
                text(record, field, mark)
            values(record, "constraints", mark, required=True)
            values(record, "risks", mark)
            values(record, "tbd", mark)
            related = values(record, "related_work_items", mark)
            if related is not None:
                for work_item in related:
                    if work_item not in work_items:
                        errors.append(
                            f"{mark}.related_work_items 引用了不存在的工作主题：{work_item}"
                        )
            materials = values(record, "materials", mark, required=True)
            if materials is not None:
                for material in materials:
                    if material not in known_materials:
                        errors.append(f"{mark}.materials 引用了不存在的材料：{material}")
            options = record.get("options")
            option_ids: set[str] = set()
            if not isinstance(options, list) or not options:
                errors.append(mark + ".options 必须是非空数组")
            else:
                for option_index, option in enumerate(options):
                    option_mark = f"{mark}.options[{option_index}]"
                    if not isinstance(option, dict):
                        errors.append(option_mark + " 必须是对象")
                        continue
                    option_id = option.get("id")
                    if (
                        not isinstance(option_id, str)
                        or not ID_RE.fullmatch(option_id)
                        or option_id in option_ids
                    ):
                        errors.append(option_mark + ".id 非法或重复")
                    else:
                        option_ids.add(option_id)
                    if not isinstance(option.get("summary"), str) or not option["summary"].strip():
                        errors.append(option_mark + ".summary 必须是非空文本")
                    for field in ("tradeoffs", "risks"):
                        value = option.get(field, [])
                        if not isinstance(value, list) or any(
                            not isinstance(entry, str) or not entry.strip() for entry in value
                        ):
                            errors.append(option_mark + f".{field} 必须是文本数组")
            panel_id = record.get("panel")
            if panel_id is not None and panel_id not in advisory_panels:
                errors.append(mark + ".panel 必须引用前序 advisory_panel")
            design_proposals[record_id] = record
        elif kind == "design_decision":
            target = round_ref()
            if target and target["id"] in closed:
                errors.append(mark + " 不能写入已关闭轮次")
            proposal_id = record.get("proposal")
            proposal = design_proposals.get(proposal_id)
            if not proposal:
                errors.append(mark + ".proposal 必须引用前序 design_proposal")
            elif proposal_id in design_decisions:
                errors.append(mark + ".proposal 已经有设计决定；后续设计请建立新提案")
            if record.get("outcome") not in DESIGN_DECISIONS:
                errors.append(mark + ".outcome 必须是 accepted、rejected 或 deferred")
            if record.get("decided_by") != "principal":
                errors.append(mark + ".decided_by 必须是 principal")
            text(record, "rationale", mark)
            materials = values(record, "materials", mark, required=True)
            if materials is not None:
                for material in materials:
                    if material not in known_materials:
                        errors.append(f"{mark}.materials 引用了不存在的材料：{material}")
            supersedes = values(record, "supersedes", mark) or []
            if supersedes and record.get("outcome") != "accepted":
                errors.append(mark + " 只有 accepted 设计可以声明 supersedes")
            for old_id in supersedes:
                if old_id == proposal_id:
                    errors.append(mark + ".supersedes 不能引用当前 proposal")
                elif old_id not in design_proposals:
                    errors.append(mark + ".supersedes 必须引用前序 design_proposal")
            values(record, "conditions", mark)
            if isinstance(proposal_id, str) and proposal_id not in design_decisions:
                design_decisions[proposal_id] = record
        elif kind == "design_artifact":
            target = round_ref()
            if target and target["id"] in closed:
                errors.append(mark + " 不能写入已关闭轮次")
            proposal_id = record.get("proposal")
            if proposal_id not in design_proposals:
                errors.append(mark + ".proposal 必须引用前序 design_proposal")
            role(record, "created_by", mark, PROPOSER_ROLES)
            text(record, "title", mark)
            text(record, "summary", mark)
            if record.get("kind") not in DESIGN_ARTIFACT_KINDS:
                errors.append(
                    mark + ".kind 必须是 " + "、".join(sorted(DESIGN_ARTIFACT_KINDS))
                )
            path_value = record.get("path")
            sha_value = record.get("sha256")
            if (path_value is None) != (sha_value is None):
                errors.append(mark + ".path 与 .sha256 必须同时出现")
            if path_value is not None and sha_value is not None:
                path, path_error = _project_file(project, path_value)
                if path_error:
                    errors.append(mark + ".path " + path_error)
                elif not isinstance(sha_value, str) or not _sha256_text().fullmatch(sha_value):
                    errors.append(mark + ".sha256 非法")
                elif _digest_file(path) != sha_value:
                    errors.append(mark + ".sha256 与文件不一致")
            materials = values(record, "materials", mark, required=True)
            if materials is not None:
                for material in materials:
                    if material not in known_materials:
                        errors.append(f"{mark}.materials 引用了不存在的材料：{material}")
            design_artifacts[record_id] = record
        elif kind == "advisory_panel":
            target = round_ref()
            if target and target["id"] in closed:
                errors.append(mark + " 不能写入已关闭轮次")
            role(record, "convened_by", mark, {"principal", "assistant_researcher"})
            for field in ("question", "mandate", "synthesis"):
                text(record, field, mark)
            if record.get("mode") not in ADVISORY_MODES:
                errors.append(mark + ".mode 必须是 replicate 或 heterogeneous")
            if record.get("status") not in ADVISORY_STATUSES:
                errors.append(mark + ".status 必须是 completed、partial 或 failed")
            members = record.get("members")
            member_ids: set[str] = set()
            if not isinstance(members, list) or len(members) < 2:
                errors.append(mark + ".members 至少需要两个独立研究顾问")
            else:
                for member_index, member in enumerate(members):
                    member_mark = f"{mark}.members[{member_index}]"
                    if not isinstance(member, dict):
                        errors.append(member_mark + " 必须是对象")
                        continue
                    advisor_id = member.get("advisor_id")
                    if (
                        not isinstance(advisor_id, str)
                        or not ID_RE.fullmatch(advisor_id)
                        or advisor_id in member_ids
                    ):
                        errors.append(member_mark + ".advisor_id 非法或重复")
                    else:
                        member_ids.add(advisor_id)
                    if member.get("role") != "research_advisor":
                        errors.append(member_mark + ".role 必须是 research_advisor")
                    for field in ("mandate", "summary"):
                        if not isinstance(member.get(field), str) or not member[field].strip():
                            errors.append(member_mark + f".{field} 必须是非空文本")
                    uncertainties = member.get("uncertainties", [])
                    if not isinstance(uncertainties, list) or any(
                        not isinstance(entry, str) or not entry.strip()
                        for entry in uncertainties
                    ):
                        errors.append(member_mark + ".uncertainties 必须是文本数组")
            values(record, "unresolved_disagreements", mark)
            materials = values(record, "materials", mark, required=True)
            if materials is not None:
                for material in materials:
                    if material not in known_materials:
                        errors.append(f"{mark}.materials 引用了不存在的材料：{material}")
            advisory_panels[record_id] = record
        elif kind == "specialist_task":
            target = round_ref()
            if target and target["id"] in closed:
                errors.append(mark + " 不能写入已关闭轮次")
            text(record, "task", mark)
            text(record, "summary", mark)
            role(record, "requested_by", mark, REQUESTER_ROLES)
            if record.get("executed_by") != "research_specialist":
                errors.append(mark + ".executed_by 必须是 research_specialist")
            if record.get("status") not in SPECIALIST_STATUSES:
                errors.append(
                    mark + ".status 必须是 completed、partial、failed 或 blocked"
                )
            values(record, "scope", mark, required=True)
            values(record, "limitations", mark)
            values(record, "unresolved", mark)
            materials = values(record, "materials", mark, required=True)
            if materials is not None:
                for material in materials:
                    if material not in known_materials:
                        errors.append(f"{mark}.materials 引用了不存在的材料：{material}")
            outputs = record.get("outputs", [])
            if not isinstance(outputs, list):
                errors.append(mark + ".outputs 必须是数组")
            else:
                for output_index, output in enumerate(outputs):
                    output_mark = f"{mark}.outputs[{output_index}]"
                    if not isinstance(output, dict):
                        errors.append(output_mark + " 必须是对象")
                        continue
                    if output.get("path") is None and output.get("sha256") is None:
                        text(output, "summary", output_mark)
                        continue
                    path, path_error = _project_file(project, output.get("path"))
                    if path_error:
                        errors.append(output_mark + ".path " + path_error)
                    elif not isinstance(output.get("sha256"), str) or not _sha256_text().fullmatch(output["sha256"]):
                        errors.append(output_mark + ".sha256 非法")
                    elif _digest_file(path) != output["sha256"]:
                        errors.append(output_mark + ".sha256 与文件不一致")
            specialist_tasks[record_id] = record
        elif kind == "alignment":
            target = round_ref()
            if target:
                if target["id"] in closed or target["id"] in aligned:
                    errors.append(mark + " 轮次已经关闭")
                current_records = [
                    item
                    for item in records[:index]
                    if item.get("round") == target["id"]
                ]
                has_review = any(item.get("type") == "review" for item in current_records)
                has_design = any(
                    item.get("type") in {"design_proposal", "design_artifact", "advisory_panel", "specialist_task"}
                    for item in current_records
                )
                process = target.get("process")
                if not has_review and not has_design:
                    errors.append(mark + " 对齐前至少需要一条复盘或设计记录")
                if process == "review" and has_design:
                    errors.append(mark + " review 轮次不能包含设计记录；混合工作应声明 mixed")
                if process == "design" and has_review:
                    errors.append(mark + " design 轮次不能包含复盘记录；混合工作应声明 mixed")
                if process in {"design", "mixed"} and not has_design:
                    errors.append(mark + f" {process} 轮次至少需要一条设计记录")
                if process == "mixed" and not has_review:
                    errors.append(mark + " mixed 轮次至少需要一条复盘记录")
                if process is None and not has_review:
                    errors.append(mark + " 旧格式轮次对齐前至少需要一条复盘记录")
                round_questions = [
                    question_id for question_id, value in questions.items()
                    if value.get("round") == target["id"]
                ]
                missing = [question_id for question_id in round_questions if question_id not in answers]
                if missing:
                    errors.append(f"{mark} 仍有问题未回答：{', '.join(missing)}")
            text(record, "summary", mark)
            if "narrative" in record:
                text(record, "narrative", mark)
            items = record.get("items")
            if items is None:
                for field in ("confirmed", "disputed", "unknown", "next_steps"):
                    values(record, field, mark)
            else:
                if not isinstance(items, list) or not items:
                    errors.append(mark + ".items 必须是非空数组")
                else:
                    item_ids: set[str] = set()
                    for item_index, item in enumerate(items):
                        item_mark = f"{mark}.items[{item_index}]"
                        if not isinstance(item, dict):
                            errors.append(item_mark + " 必须是对象")
                            continue
                        item_id = item.get("id")
                        if (
                            not isinstance(item_id, str)
                            or not ID_RE.fullmatch(item_id)
                            or item_id in item_ids
                        ):
                            errors.append(item_mark + ".id 非法或重复")
                        else:
                            item_ids.add(item_id)
                        if not isinstance(item.get("statement"), str) or not item["statement"].strip():
                            errors.append(item_mark + ".statement 必须是非空文本")
                        if item.get("status") not in ALIGNMENT_STATUSES:
                            errors.append(item_mark + ".status 非法")
                        materials = item.get("materials", [])
                        if not isinstance(materials, list) or any(
                            not isinstance(value, str) or not value.strip() for value in materials
                        ):
                            errors.append(item_mark + ".materials 必须是文本数组")
                        else:
                            for material in materials:
                                if material not in known_materials:
                                    errors.append(
                                        f"{item_mark}.materials 引用了不存在的材料：{material}"
                                    )
                        related_items = item.get("related_work_items", [])
                        if not isinstance(related_items, list) or any(
                            not isinstance(value, str) or not value.strip()
                            for value in related_items
                        ):
                            errors.append(item_mark + ".related_work_items 必须是文本数组")
                        else:
                            for work_item in related_items:
                                if work_item not in work_items:
                                    errors.append(
                                        f"{item_mark}.related_work_items 引用了不存在的工作主题：{work_item}"
                                    )
                next_steps = record.get("next_steps", [])
                if not isinstance(next_steps, list) or any(
                    not isinstance(entry, str) or not entry.strip() for entry in next_steps
                ):
                    errors.append(mark + ".next_steps 必须是文本数组")
            if target and target["id"] not in closed:
                aligned.add(target["id"])
                closed.add(target["id"])
                if isinstance(record.get("model_sha256"), str):
                    alignment_hashes[target["id"]] = record["model_sha256"]
            if not isinstance(record.get("model_sha256"), str) or not re.fullmatch(
                r"[0-9a-f]{64}", record["model_sha256"]
            ):
                errors.append(mark + ".model_sha256 必须是模型摘要")
        elif kind == "snapshot":
            target = round_ref()
            if record.get("project") != load_json(project / "project.json", {}).get("id"):
                errors.append(mark + ".project 与工作区不一致")
            if target and target["id"] not in closed:
                errors.append(mark + " 只能冻结已对齐关闭的轮次")
            text(record, "project", mark)
            text(record, "label", mark)
            text(record, "path", mark)
            text(record, "sha256", mark)
            baseline_kind = record.get("baseline_kind")
            if baseline_kind is not None and baseline_kind not in BASELINE_KINDS:
                errors.append(mark + ".baseline_kind 必须是 knowledge、design 或 mixed")
            expected = Path("synthesis/snapshots") / record_id / "snapshot.json"
            if record.get("path") != expected.as_posix():
                errors.append(f"{mark}.path 必须是 {expected.as_posix()}")
            else:
                snapshot_file = project / expected
                if not snapshot_file.is_file():
                    errors.append(mark + " 快照文件不存在")
                elif record.get("sha256") != _digest_file(snapshot_file):
                    errors.append(mark + " 快照哈希不一致")
                else:
                    try:
                        snapshot = json.loads(snapshot_file.read_text(encoding="utf-8-sig"))
                    except (OSError, ValueError) as exc:
                        errors.append(f"{mark} 快照不可读：{exc}")
                    else:
                        if not isinstance(snapshot, dict) or snapshot.get("schema") != SNAPSHOT_SCHEMA:
                            errors.append(f"{mark} snapshot schema 必须是 {SNAPSHOT_SCHEMA}")
                        else:
                            if snapshot.get("id") != record_id:
                                errors.append(f"{mark} 快照 id 不一致")
                            if snapshot.get("project") != record.get("project"):
                                errors.append(f"{mark} 快照 project 不一致")
                            if snapshot.get("round") != record.get("round"):
                                errors.append(f"{mark} 快照 round 不一致")
                            if baseline_kind is not None and snapshot.get("baseline_kind") != baseline_kind:
                                errors.append(f"{mark} 快照 baseline_kind 不一致")
                            snapshot_model = snapshot.get("model")
                            if not isinstance(snapshot_model, dict):
                                errors.append(f"{mark} 快照缺少 model")
                            elif snapshot.get("model_sha256") != _model_digest(snapshot_model):
                                errors.append(f"{mark} 快照 model_sha256 不一致")
                            elif snapshot.get("model_sha256") != alignment_hashes.get(record.get("round")):
                                errors.append(f"{mark} 快照未绑定本轮对齐时的模型版本")
                            if baseline_kind in {"design", "mixed"}:
                                if not isinstance(snapshot.get("design_baseline"), dict):
                                    errors.append(f"{mark} 快照缺少 design_baseline")
                                elif snapshot["design_baseline"].get("schema") != "sa.design-baseline/1":
                                    errors.append(f"{mark}.design_baseline schema 非法")
            if target:
                snapshot_rounds[record_id] = target["id"]
        elif kind == "decision":
            target = round_ref()
            if not target:
                pass
            elif target["id"] not in closed:
                errors.append(mark + " 只能对已对齐关闭的轮次作决定")
            elif target["id"] not in snapshot_rounds.values():
                errors.append(mark + " 作决定前必须冻结轮次快照")
            if record.get("round") in decision_rounds:
                errors.append(mark + " 每个轮次只能登记一次循环决定")
            if record.get("actor") not in {"principal", "user"}:
                errors.append(mark + ".actor 必须是 principal（旧记录兼容 user）")
            if record.get("decision") not in ROUND_DECISIONS:
                errors.append(mark + ".decision 非法")
            text(record, "rationale", mark)
            materials = values(record, "materials", mark, required=True)
            if materials is not None:
                for material in materials:
                    if material not in known_materials:
                        errors.append(f"{mark}.materials 引用了不存在的材料：{material}")
            if record.get("decision") == "drill_down":
                target_topic = record.get("target_topic")
                if not isinstance(target_topic, str) or not ID_RE.fullmatch(target_topic):
                    errors.append(mark + ".target_topic 必须是小写 ID")
                text(record, "target_title", mark)
            if record.get("decision") == "park":
                text(record, "resume_when", mark)
            if record.get("round") in rounds:
                decision_rounds.add(record["round"])
        seen[record_id] = record
        if kind == "round":
            open_ids = set(rounds) - closed
            if open_ids:
                errors.append(mark + " 新建轮次前必须关闭当前轮次")
            rounds[record_id] = record
            if isinstance(record.get("topic"), str):
                round_topics[record_id] = record["topic"]
                topics.add(record["topic"])
    return errors


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
    records = data.get("records")
    if not isinstance(records, list):
        return errors + ["synthesis ledger records 必须是数组"]
    model_file = model_path(project)
    if not model_file.is_file():
        return errors + ["缺少 work-model/model.json"]
    try:
        model = json.loads(model_file.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return errors + [f"work model 不是合法 JSON：{exc}"]
    model_errors = _validate_work_model(project, model, meta)
    errors.extend(model_errors)
    if not model_errors:
        work_items = {item["id"] for item in model.get("items", []) if isinstance(item, dict)}
        errors.extend(_validate_records(
            project,
            records,
            _known_material_ids(project),
            work_items,
        ))
    return errors


@contextmanager
def _writer(project: Path):
    directory = project / "synthesis"
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / ".synthesis.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise ProjectError("synthesis 记录正被写入；确认无写者后再处理锁") from exc
    try:
        with handle:
            handle.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)


def _load_ledger(project: Path) -> dict:
    path = ledger_path(project)
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ProjectError(f"synthesis ledger 不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ProjectError(f"synthesis ledger schema 必须是 {SCHEMA}")
    meta = load_json(project / "project.json", {}) or {}
    if data.get("project") != meta.get("id"):
        raise ProjectError("synthesis ledger project 与 project.json 不一致")
    if not isinstance(data.get("records"), list):
        raise ProjectError("synthesis ledger records 必须是数组")
    return data


def _save_ledger(project: Path, data: dict) -> None:
    path = ledger_path(project)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def apply_records(project: Path | str, records) -> int:
    project = Path(project).resolve()
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list) or not records:
        raise ProjectError("输入必须是非空记录数组或单条记录")
    with _writer(project):
        data = _load_ledger(project)
        model = load_json(model_path(project), {}) or {}
        meta = load_json(project / "project.json", {}) or {}
        model_errors = _validate_work_model(project, model, meta)
        if model_errors:
            raise ProjectError("\n".join(model_errors))
        model_sha256 = _model_digest(model)
        for value in records:
            record = json.loads(json.dumps(value, ensure_ascii=False))
            if not isinstance(record, dict):
                raise ProjectError("每条记录必须是对象")
            if record.get("type") == "snapshot":
                raise ProjectError("snapshot 记录必须由 sa synthesis snapshot 创建")
            record.setdefault("at", _now())
            if record.get("type") in {"review", "correction", "alignment"}:
                record["model_sha256"] = model_sha256
            data["records"].append(record)
        errors = _validate_records(
            project,
            data["records"],
            _known_material_ids(project),
            {item["id"] for item in model.get("items", []) if isinstance(item, dict)},
        )
        if errors:
            raise ProjectError("\n".join(errors))
        _save_ledger(project, data)
    return len(records)


def _build_design_baseline(records: list[dict]) -> dict:
    proposals = [record for record in records if record.get("type") == "design_proposal"]
    decisions = {
        record["proposal"]: record
        for record in records
        if record.get("type") == "design_decision"
    }
    artifacts_by_proposal: dict[str, list[dict]] = {}
    for record in records:
        if record.get("type") == "design_artifact":
            artifacts_by_proposal.setdefault(record["proposal"], []).append(record)
    superseded = {
        old_id
        for decision in decisions.values()
        if decision.get("outcome") == "accepted"
        for old_id in decision.get("supersedes", [])
    }
    proposal_states = []
    for proposal in proposals:
        proposal_id = proposal["id"]
        decision = decisions.get(proposal_id)
        effective_status = (
            "superseded"
            if proposal_id in superseded
            else decision.get("outcome", "proposed")
            if decision
            else "proposed"
        )
        proposal_states.append({
            **json.loads(json.dumps(proposal, ensure_ascii=False)),
            "effective_status": effective_status,
            "decision": (
                json.loads(json.dumps(decision, ensure_ascii=False))
                if decision
                else None
            ),
            "artifacts": [
                json.loads(json.dumps(artifact, ensure_ascii=False))
                for artifact in artifacts_by_proposal.get(proposal_id, [])
            ],
        })
    return {
        "schema": "sa.design-baseline/1",
        "proposals": proposal_states,
        "advisory_panels": [
            json.loads(json.dumps(record, ensure_ascii=False))
            for record in records
            if record.get("type") == "advisory_panel"
        ],
        "specialist_tasks": [
            json.loads(json.dumps(record, ensure_ascii=False))
            for record in records
            if record.get("type") == "specialist_task"
        ],
    }


def create_snapshot(
    project: Path | str,
    snapshot_id: str,
    label: str,
    round_id: str,
    baseline_kind: str | None = None,
) -> Path:
    project = Path(project).resolve()
    if not isinstance(snapshot_id, str) or not ID_RE.fullmatch(snapshot_id):
        raise ProjectError("snapshot id 格式非法")
    if not isinstance(label, str) or not label.strip():
        raise ProjectError("snapshot label 不能为空")
    if baseline_kind is not None and baseline_kind not in BASELINE_KINDS:
        raise ProjectError("snapshot baseline_kind 必须是 knowledge、design 或 mixed")
    with _writer(project):
        data = _load_ledger(project)
        if any(record.get("id") == snapshot_id for record in data["records"]):
            raise ProjectError("snapshot id 已使用")
        round_record = next(
            (
                record for record in data["records"]
                if record.get("id") == round_id and record.get("type") == "round"
            ),
            None,
        )
        if not round_record:
            raise ProjectError("snapshot 必须引用已有 round")
        alignment = next(
            (
                record for record in data["records"]
                if record.get("type") == "alignment" and record.get("round") == round_id
            ),
            None,
        )
        if not alignment:
            raise ProjectError("轮次尚未完成对齐，不能冻结 snapshot")
        model = load_json(model_path(project), {}) or {}
        meta = load_json(project / "project.json", {}) or {}
        model_errors = _validate_work_model(project, model, meta)
        if model_errors:
            raise ProjectError("\n".join(model_errors))
        current_model_sha256 = _model_digest(model)
        if alignment.get("model_sha256") != current_model_sha256:
            raise ProjectError("工作模型在对齐后已变化；请新建轮次重新对齐后再冻结")
        round_records = [
            record for record in data["records"]
            if record.get("round") == round_id
        ]
        has_review = any(record.get("type") == "review" for record in round_records)
        has_design = any(record.get("type") in DESIGN_RECORD_TYPES for record in round_records)
        if baseline_kind is None:
            process = round_record.get("process")
            if process == "design":
                baseline_kind = "design"
            elif process == "mixed":
                baseline_kind = "mixed"
            elif process == "review":
                baseline_kind = "knowledge"
            elif has_design and has_review:
                baseline_kind = "mixed"
            elif has_design:
                baseline_kind = "design"
            else:
                baseline_kind = "knowledge"
        if baseline_kind == "knowledge" and has_design:
            raise ProjectError("knowledge baseline 不能冻结包含设计记录的轮次")
        if baseline_kind in {"design", "mixed"} and not has_design:
            raise ProjectError(f"{baseline_kind} baseline 需要至少一条设计记录")
        relative_path = Path("synthesis/snapshots") / snapshot_id / "snapshot.json"
        snapshot_file = project / relative_path
        if snapshot_file.parent.exists():
            raise ProjectError("snapshot 目录已存在；可能有未登记的中断产物")
        snapshot_file.parent.mkdir(parents=True)
        snapshot = {
            "schema": SNAPSHOT_SCHEMA,
            "id": snapshot_id,
            "project": meta.get("id"),
            "round": round_id,
            "topic": round_record.get("topic"),
            "topic_title": round_record.get("topic_title") or round_record.get("goal"),
            "related_work_items": round_record.get("related_work_items", []),
            "label": label.strip(),
            "created_at": _now(),
            "as_of": model["as_of"],
            "model_sha256": current_model_sha256,
            "source_manifest_sha256": _digest_file(
                project / "brief/provided/manifest.json"
            ),
            "baseline_kind": baseline_kind,
            "model": model,
        }
        if baseline_kind in {"design", "mixed"}:
            snapshot["design_baseline"] = _build_design_baseline(data["records"])
        try:
            snapshot_file.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            record = {
                "id": snapshot_id,
                "type": "snapshot",
                "at": _now(),
                "project": meta.get("id"),
                "round": round_id,
                "label": label.strip(),
                "path": relative_path.as_posix(),
                "sha256": _digest_file(snapshot_file),
                "baseline_kind": baseline_kind,
            }
            records = data["records"] + [record]
            errors = _validate_records(
                project,
                records,
                _known_material_ids(project),
                {item["id"] for item in model.get("items", []) if isinstance(item, dict)},
            )
            if errors:
                raise ProjectError("\n".join(errors))
            _save_ledger(project, {**data, "records": records})
        except Exception:
            snapshot_file.unlink(missing_ok=True)
            snapshot_file.parent.rmdir()
            raise
    return snapshot_file


def load_work_snapshot(project: Path | str, snapshot_id: str) -> dict:
    project = Path(project).resolve()
    errors = validate_synthesis(project)
    if errors:
        raise ProjectError("\n".join(errors))
    data = _load_ledger(project)
    record = next(
        (
            item for item in data["records"]
            if item.get("type") == "snapshot" and item.get("id") == snapshot_id
        ),
        None,
    )
    if not record:
        raise ProjectError(f"snapshot 不存在：{snapshot_id}")
    path = (project / record["path"]).resolve()
    if not path.is_relative_to(project) or not path.is_file():
        raise ProjectError(f"snapshot 文件不存在或越出项目：{record['path']}")
    if _digest_file(path) != record["sha256"]:
        raise ProjectError(f"snapshot 哈希不一致：{snapshot_id}")
    snapshot = json.loads(path.read_text(encoding="utf-8-sig"))
    if snapshot.get("schema") != SNAPSHOT_SCHEMA:
        raise ProjectError(f"snapshot schema 必须是 {SNAPSHOT_SCHEMA}")
    baseline_kind = snapshot.get("baseline_kind")
    if baseline_kind is not None and baseline_kind not in BASELINE_KINDS:
        raise ProjectError("snapshot baseline_kind 必须是 knowledge、design 或 mixed")
    if baseline_kind in {"design", "mixed"}:
        design = snapshot.get("design_baseline")
        if not isinstance(design, dict) or design.get("schema") != "sa.design-baseline/1":
            raise ProjectError("snapshot design_baseline schema 非法")
    meta = load_json(project / "project.json", {}) or {}
    if snapshot.get("project") != meta.get("id"):
        raise ProjectError("snapshot project 与 project.json 不一致")
    model_errors = _validate_work_model(project, snapshot.get("model", {}), meta)
    if model_errors:
        raise ProjectError("\n".join(model_errors))
    return snapshot


def synthesis_status(project: Path | str) -> dict:
    project = Path(project).resolve()
    errors = validate_synthesis(project)
    if errors:
        raise ProjectError("\n".join(errors))
    data = _load_ledger(project)
    model = load_json(model_path(project), {}) or {}
    records = data["records"]
    answers = {
        record["question"]: record
        for record in records
        if record.get("type") == "answer"
    }
    aligned = {
        record["round"]
        for record in records
        if record.get("type") == "alignment"
    }
    decisions = {
        record["round"]: record
        for record in records
        if record.get("type") == "decision"
    }
    rounds = []
    for record in records:
        if record.get("type") != "round":
            continue
        round_id = record["id"]
        questions = [
            {
                "id": question["id"],
                "text": question["text"],
                "priority": question["priority"],
                "answer": answers.get(question["id"], {}).get("status", "unanswered"),
            }
            for question in records
            if question.get("type") == "question" and question.get("round") == round_id
        ]
        rounds.append({
            "id": round_id,
            "process": record.get("process"),
            "topic": record.get("topic"),
            "topic_title": record.get("topic_title") or record["goal"],
            "related_work_items": record.get("related_work_items", []),
            "parent_topic": record.get("parent_topic"),
            "parent_snapshot": record.get("parent_snapshot"),
            "goal": record["goal"],
            "status": "closed" if round_id in aligned else "open",
            "decision": decisions.get(round_id, {}).get("decision", "pending"),
            "reviews": sum(
                1 for item in records
                if item.get("type") == "review" and item.get("round") == round_id
            ),
            "questions": questions,
            "design_proposals": sum(
                1 for item in records
                if item.get("type") == "design_proposal" and item.get("round") == round_id
            ),
            "design_decisions": sum(
                1 for item in records
                if item.get("type") == "design_decision" and item.get("round") == round_id
            ),
            "advisory_panels": sum(
                1 for item in records
                if item.get("type") == "advisory_panel" and item.get("round") == round_id
            ),
            "specialist_tasks": sum(
                1 for item in records
                if item.get("type") == "specialist_task" and item.get("round") == round_id
            ),
        })
    snapshots = [
        {
            "id": record["id"],
            "round": record["round"],
            "label": record["label"],
            "path": record["path"],
            "baseline_kind": record.get("baseline_kind", "knowledge"),
        }
        for record in records
        if record.get("type") == "snapshot"
    ]
    snapshot_rounds = {
        record["id"]: record["round"]
        for record in records
        if record.get("type") == "snapshot"
    }
    children: dict[str, list[str]] = {}
    for record in records:
        if record.get("type") == "round" and record.get("parent_snapshot"):
            parent_round = snapshot_rounds.get(record["parent_snapshot"])
            if parent_round:
                children.setdefault(parent_round, []).append(record["id"])
    for round_record in rounds:
        round_record["children"] = children.get(round_record["id"], [])
    design_records = any(
        record.get("type") in DESIGN_RECORD_TYPES
        for record in records
    )
    return {
        "schema": SCHEMA,
        "project": data["project"],
        "model_sha256": _model_digest(model),
        "rounds": rounds,
        "snapshots": snapshots,
        "design_baseline": _build_design_baseline(records) if design_records else None,
        "records": len(records),
    }


def _markdown_cell(value: str) -> str:
    return " ".join(value.split()).replace("|", "\\|")


def _alignment_items(alignment: dict) -> list[dict]:
    if isinstance(alignment.get("items"), list):
        return alignment["items"]
    items: list[dict] = []
    number = 1
    for status in ("confirmed", "disputed", "unknown"):
        for statement in alignment.get(status, []):
            items.append({
                "id": f"legacy-{number:04d}",
                "statement": statement,
                "status": status,
                "materials": [],
                "related_work_items": [],
            })
            number += 1
    return items


def render_alignment_record(project: Path | str, round_id: str) -> Path:
    project = Path(project).resolve()
    errors = validate_synthesis(project)
    if errors:
        raise ProjectError("\n".join(errors))
    data = _load_ledger(project)
    records = data["records"]
    round_record = next(
        (
            record for record in records
            if record.get("type") == "round" and record.get("id") == round_id
        ),
        None,
    )
    if not round_record:
        raise ProjectError(f"round 不存在：{round_id}")
    alignment = next(
        (
            record for record in records
            if record.get("type") == "alignment" and record.get("round") == round_id
        ),
        None,
    )
    if not alignment:
        raise ProjectError("轮次尚未完成对齐，不能生成正式 alignment 记录")
    round_records = [
        record for record in records
        if record.get("round") == round_id
    ]
    reviews = [record for record in round_records if record.get("type") == "review"]
    questions = [record for record in round_records if record.get("type") == "question"]
    answers = {
        record["question"]: record
        for record in round_records
        if record.get("type") == "answer"
    }
    corrections = [
        record for record in round_records if record.get("type") == "correction"
    ]
    design_proposals = [
        record for record in round_records if record.get("type") == "design_proposal"
    ]
    design_decisions = {
        record["proposal"]: record
        for record in records
        if record.get("type") == "design_decision"
    }
    current_design_decisions = [
        design_decisions[proposal["id"]]
        for proposal in design_proposals
        if proposal["id"] in design_decisions
    ]
    design_artifacts = [
        record for record in round_records if record.get("type") == "design_artifact"
    ]
    advisory_panels = [
        record for record in round_records if record.get("type") == "advisory_panel"
    ]
    specialist_tasks = [
        record for record in round_records if record.get("type") == "specialist_task"
    ]
    decision = next(
        (
            record for record in records
            if record.get("type") == "decision" and record.get("round") == round_id
        ),
        None,
    )
    snapshots = [
        record for record in records
        if record.get("type") == "snapshot" and record.get("round") == round_id
    ]
    material_ids = sorted({
        material
        for record in [
            round_record,
            *reviews,
            *questions,
            *answers.values(),
            *corrections,
            *design_proposals,
            *design_artifacts,
            *advisory_panels,
            *specialist_tasks,
            *current_design_decisions,
        ]
        for material in record.get("materials", [])
    })
    topic_title = round_record.get("topic_title") or round_record.get("goal") or round_id
    topic = round_record.get("topic")
    lines = [
        f"# Alignment {round_id} · {topic_title}",
        "",
        "> 本文件由 `sa synthesis alignment` 从 `synthesis/ledger.json` 生成，请勿手工编辑。",
        "",
        "## 元信息",
        "",
        f"- 项目：`{data['project']}`",
        f"- 轮次：`{round_id}`",
    ]
    if topic:
        lines.append(f"- 主题 ID：`{topic}`")
    if round_record.get("process"):
        lines.append(f"- 轮次过程：`{round_record['process']}`")
    lines.extend([
        f"- 相关工作主题：{'、'.join(f'`{value}`' for value in round_record.get('related_work_items', [])) or '无'}",
        f"- 对齐模型摘要：`{alignment.get('model_sha256', '')}`",
        f"- 使用材料：{'、'.join(f'`{value}`' for value in material_ids) or '无'}",
        "",
        "## 完整叙述",
        "",
        alignment.get("narrative") or alignment.get("summary", ""),
        "",
        "## 复盘摘要",
        "",
    ])
    if reviews:
        lines.extend(f"- {review['summary']}" for review in reviews)
    else:
        lines.append("- 未记录复盘摘要")
    lines.extend(["", "## 设计记录", ""])
    if design_proposals:
        lines.extend([
            "| 提案 | 标题 | 提出者 | 有效状态 | 依据 |",
            "|---|---|---|---|---|",
        ])
        superseded = {
            old_id
            for decision in design_decisions.values()
            if decision.get("outcome") == "accepted"
            for old_id in decision.get("supersedes", [])
        }
        for proposal in design_proposals:
            design_decision = design_decisions.get(proposal["id"])
            status = (
                "superseded"
                if proposal["id"] in superseded
                else design_decision.get("outcome", "proposed")
                if design_decision
                else "proposed"
            )
            lines.append(
                "| "
                + " | ".join([
                    _markdown_cell(proposal["id"]),
                    _markdown_cell(proposal["title"]),
                    _markdown_cell(proposal["proposed_by"]),
                    _markdown_cell(status),
                    _markdown_cell(
                        design_decision.get("rationale", "")
                        if design_decision
                        else ""
                    ),
                ])
                + " |"
            )
    else:
        lines.append("- 本轮没有设计提案")
    if design_artifacts:
        lines.extend(["", "### 设计产物", ""])
        for artifact in design_artifacts:
            path = f"；文件 `{artifact['path']}`" if artifact.get("path") else ""
            lines.append(
                f"- `{artifact['id']}` {artifact['title']}（{artifact['kind']}）"
                f"：{artifact['summary']}{path}"
            )
    if advisory_panels:
        lines.extend(["", "### 研究顾问委员会", ""])
        for panel in advisory_panels:
            lines.append(
                f"- `{panel['id']}` {panel['question']}（{panel['mode']}，"
                f"{len(panel['members'])} 位研究顾问）：{panel['synthesis']}"
            )
            for member in panel["members"]:
                lines.append(
                    f"  - `{member['advisor_id']}`：{member['summary']}"
                )
    if specialist_tasks:
        lines.extend(["", "### 研究专员任务", ""])
        for task in specialist_tasks:
            lines.append(
                f"- `{task['id']}` {task['task']}（{task['status']}）：{task['summary']}"
            )
    lines.extend(["", "## 问题与回答", ""])
    if questions:
        lines.extend(["| 问题 | 优先级 | 回答状态 | 回答摘要 |", "|---|---|---|---|"])
        for question in questions:
            answer = answers.get(question["id"], {})
            lines.append(
                "| "
                + " | ".join([
                    _markdown_cell(question["text"]),
                    _markdown_cell(question["priority"]),
                    _markdown_cell(answer.get("status", "unanswered")),
                    _markdown_cell(answer.get("summary", "")),
                ])
                + " |"
            )
    else:
        lines.append("- 本轮没有登记问题")
    lines.extend(["", "## 修正记录", ""])
    if corrections:
        for correction in corrections:
            lines.append(
                f"- `{correction['target']}`：{correction['summary']}"
            )
    else:
        lines.append("- 无修正记录")
    lines.extend(["", "## 对齐结论", ""])
    items = _alignment_items(alignment)
    if items:
        lines.extend([
            "| 条目 | 判断 | 结论 | 工作主题 | 材料 |",
            "|---|---|---|---|---|",
        ])
        labels = {
            "confirmed": "已确认",
            "disputed": "有争议",
            "unknown": "未知",
            "deferred": "暂缓",
            "out_of_scope": "不属于本轮",
            "accepted": "已接受设计",
            "rejected": "已否决设计",
            "superseded": "已被替代",
        }
        for item in items:
            lines.append(
                "| "
                + " | ".join([
                    _markdown_cell(item["id"]),
                    labels[item["status"]],
                    _markdown_cell(item["statement"]),
                    _markdown_cell("、".join(item.get("related_work_items", []))),
                    _markdown_cell("、".join(item.get("materials", []))),
                ])
                + " |"
            )
    else:
        lines.append("- 无结构化对齐条目")
    next_steps = alignment.get("next_steps", [])
    lines.extend(["", "## 下一步", ""])
    lines.extend(f"- {value}" for value in next_steps) if next_steps else lines.append("- 无")
    lines.extend(["", "## 循环出口", ""])
    if decision:
        decision_label = {
            "exit": "跳出当前循环",
            "continue": "继续当前主题",
            "drill_down": "展开下层主题",
            "park": "暂挂当前主题",
        }[decision["decision"]]
        lines.append(f"- 首席研究员决定：{decision_label}")
        lines.append(f"- 理由：{decision['rationale']}")
        if decision.get("target_topic"):
            lines.append(
                f"- 目标主题：`{decision['target_topic']}` {decision.get('target_title', '')}"
            )
        if decision.get("resume_when"):
            lines.append(f"- 重启条件：{decision['resume_when']}")
    else:
        lines.append("- 待首席研究员决定")
    lines.extend(["", "## 冻结快照", ""])
    if snapshots:
        for snapshot in snapshots:
            snapshot_link = Path(snapshot["path"]).relative_to("synthesis").as_posix()
            lines.append(
                f"- `{snapshot['id']}`：{snapshot['label']}，"
                f"{snapshot.get('baseline_kind', 'knowledge')} baseline，"
                f"[读取快照](../{snapshot_link})"
            )
    else:
        lines.append("- 尚未冻结快照")
    lines.append("")
    output = project / "synthesis/alignments" / f"{round_id}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(".tmp")
    try:
        tmp.write_text("\n".join(lines), encoding="utf-8")
        os.replace(tmp, output)
    finally:
        tmp.unlink(missing_ok=True)
    return output


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


def render_summary_markdown(
    project: Path | str,
    model: dict | None = None,
    design_baseline: dict | None = None,
) -> Path:
    project = Path(project)
    errors = validate_synthesis(project)
    if errors:
        raise ProjectError("\n".join(errors))
    meta = load_json(project / "project.json", {}) or {}
    model = model or load_json(model_path(project), {}) or {}
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
    lines.extend(["## 概览", "", model.get("overview") or "首席研究员未提供概览。", ""])
    if design_baseline:
        proposals = design_baseline.get("proposals", [])
        lines.extend([
            "## 设计基线",
            "",
            "| 提案 | 标题 | 状态 | 决定依据 |",
            "|---|---|---|---|",
        ])
        if proposals:
            for proposal in proposals:
                decision = proposal.get("decision") or {}
                lines.append(
                    f"| {proposal['id']} | {proposal['title']} | "
                    f"{proposal.get('effective_status', 'proposed')} | "
                    f"{decision.get('rationale', '')} |"
                )
        else:
            lines.append("| 无 | 无 | proposed | 尚未形成设计提案 |")
        lines.append("")
        artifacts = [
            artifact
            for proposal in proposals
            for artifact in proposal.get("artifacts", [])
        ]
        if artifacts:
            lines.extend(["### 设计产物", ""])
            for artifact in artifacts:
                path = f"；文件：`{artifact['path']}`" if artifact.get("path") else ""
                lines.append(
                    f"- `{artifact['id']}` {artifact['title']}：{artifact['summary']}{path}"
                )
            lines.append("")
        if design_baseline.get("advisory_panels"):
            lines.extend(["### 研究顾问委员会", ""])
            for panel in design_baseline["advisory_panels"]:
                lines.append(
                    f"- {panel['question']}：{panel['synthesis']} "
                    f"（{len(panel['members'])} 位研究顾问）"
                )
            lines.append("")
        if design_baseline.get("specialist_tasks"):
            lines.extend(["### 研究专员任务", ""])
            for task in design_baseline["specialist_tasks"]:
                lines.append(f"- {task['task']}：{task['summary']}（{task['status']}）")
            lines.append("")
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
        lines.extend(["## 工作主题", "", "首席研究员尚未提供可归纳的工作主题。", ""])
    lines.extend(["## 未知与待确认", "", _bullets(model.get("unknowns", [])), ""])
    output = project / "report/work-summary.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def build_synthesis_document(
    project: Path | str,
    model: dict | None = None,
    snapshot_id: str | None = None,
    design_baseline: dict | None = None,
) -> dict:
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

    overview = model.get("overview") or "首席研究员未提供概览。"
    section("overview", "概览", [{
        "type": "paragraph",
        "layer": "inference",
        "text": overview,
    }])

    if design_baseline:
        proposals = design_baseline.get("proposals", [])
        design_blocks = [{
            "type": "table",
            "layer": "inference",
            "columns": ["提案", "标题", "状态", "决定依据"],
            "rows": [
                [
                    proposal["id"],
                    proposal["title"],
                    proposal.get("effective_status", "proposed"),
                    (proposal.get("decision") or {}).get("rationale", ""),
                ]
                for proposal in proposals
            ] or [["无", "无", "proposed", "尚未形成设计提案"]],
        }]
        artifacts = [
            artifact
            for proposal in proposals
            for artifact in proposal.get("artifacts", [])
        ]
        if artifacts:
            design_blocks.extend([
                {"type": "heading", "level": 3, "text": "设计产物"},
                {
                    "type": "list",
                    "layer": "inference",
                    "items": [
                        f"{artifact['id']} {artifact['title']}：{artifact['summary']}"
                        for artifact in artifacts
                    ],
                },
            ])
        if design_baseline.get("advisory_panels"):
            design_blocks.extend([
                {"type": "heading", "level": 3, "text": "研究顾问委员会"},
                {
                    "type": "list",
                    "layer": "inference",
                    "items": [
                        f"{panel['question']}：{panel['synthesis']}"
                        for panel in design_baseline["advisory_panels"]
                    ],
                },
            ])
        if design_baseline.get("specialist_tasks"):
            design_blocks.extend([
                {"type": "heading", "level": 3, "text": "研究专员任务"},
                {
                    "type": "list",
                    "layer": "inference",
                    "items": [
                        f"{task['task']}：{task['summary']}（{task['status']}）"
                        for task in design_baseline["specialist_tasks"]
                    ],
                },
            ])
        section("design-baseline", "设计基线", design_blocks)

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
        "text": "首席研究员尚未提供可归纳的工作主题。",
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
        "generated_from": (
            f"synthesis/snapshots/{snapshot_id}/snapshot.json"
            if snapshot_id
            else "work-model/model.json"
        ),
        "snapshot": snapshot_id,
        "layer_source": "explicit",
    }


def build_synthesis_report(
    project: Path | str,
    *,
    docx: bool = False,
    snapshot_id: str | None = None,
) -> dict:
    project = Path(project)
    model = None
    design_baseline = None
    if snapshot_id:
        snapshot = load_work_snapshot(project, snapshot_id)
        model = snapshot["model"]
        design_baseline = snapshot.get("design_baseline")
    source = render_summary_markdown(
        project,
        model=model,
        design_baseline=design_baseline,
    )
    from .render import render_html, write_document

    document = build_synthesis_document(
        project,
        model=model,
        snapshot_id=snapshot_id,
        design_baseline=design_baseline,
    )
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
