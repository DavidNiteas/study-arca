"""Synthesis work models, review/alignment ledgers and frozen snapshots."""
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
    "round", "review", "question", "answer", "correction", "alignment", "snapshot", "decision"
}
QUESTION_PRIORITIES = {"high", "medium", "low"}
ANSWER_STATUSES = {"answered", "unknown", "skipped", "deferred"}
ALIGNMENT_STATUSES = {"confirmed", "disputed", "unknown", "deferred", "out_of_scope"}
ROUND_DECISIONS = {"exit", "continue", "drill_down", "park"}
ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,79}$")
LAYER_LABELS = {
    "user_statement": "用户陈述",
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
        "复盘-对齐事件通过 `sa synthesis apply --file <records.json>` 追加；"
        "关闭轮次后使用 `sa synthesis snapshot` 冻结工作模型，"
        "正式呈现使用 `sa synthesis build --snapshot <id>`。\n",
        encoding="utf-8",
    )
    (project / "work-model/README.md").write_text(
        "# 工作模型\n\n"
        "保存从用户材料归一化得到的工作主题、进展、结果、阻塞、依赖和未知项。"
        "代理归纳必须能回指 `brief/provided/` 中的材料。\n\n"
        "这里是一轮轮复盘迭代后的当前工作态；正式输出应绑定 "
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
                        errors.append(mark + " 父轮次缺少用户循环出口决定")
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
        elif kind == "alignment":
            target = round_ref()
            if target:
                if target["id"] in closed or target["id"] in aligned:
                    errors.append(mark + " 轮次已经关闭")
                if not reviews.get(target["id"]):
                    errors.append(mark + " 对齐前至少需要一条复盘记录")
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
                            snapshot_model = snapshot.get("model")
                            if not isinstance(snapshot_model, dict):
                                errors.append(f"{mark} 快照缺少 model")
                            elif snapshot.get("model_sha256") != _model_digest(snapshot_model):
                                errors.append(f"{mark} 快照 model_sha256 不一致")
                            elif snapshot.get("model_sha256") != alignment_hashes.get(record.get("round")):
                                errors.append(f"{mark} 快照未绑定本轮对齐时的模型版本")
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
            if record.get("actor") != "user":
                errors.append(mark + ".actor 必须是 user")
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


def create_snapshot(
    project: Path | str,
    snapshot_id: str,
    label: str,
    round_id: str,
) -> Path:
    project = Path(project).resolve()
    if not isinstance(snapshot_id, str) or not ID_RE.fullmatch(snapshot_id):
        raise ProjectError("snapshot id 格式非法")
    if not isinstance(label, str) or not label.strip():
        raise ProjectError("snapshot label 不能为空")
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
            "model": model,
        }
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
        })
    snapshots = [
        {
            "id": record["id"],
            "round": record["round"],
            "label": record["label"],
            "path": record["path"],
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
    return {
        "schema": SCHEMA,
        "project": data["project"],
        "model_sha256": _model_digest(model),
        "rounds": rounds,
        "snapshots": snapshots,
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
        for record in [round_record, *reviews, *questions, *answers.values(), *corrections]
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
        lines.append(f"- 用户决定：{decision_label}")
        lines.append(f"- 理由：{decision['rationale']}")
        if decision.get("target_topic"):
            lines.append(
                f"- 目标主题：`{decision['target_topic']}` {decision.get('target_title', '')}"
            )
        if decision.get("resume_when"):
            lines.append(f"- 重启条件：{decision['resume_when']}")
    else:
        lines.append("- 待用户决定")
    lines.extend(["", "## 冻结快照", ""])
    if snapshots:
        for snapshot in snapshots:
            snapshot_link = Path(snapshot["path"]).relative_to("synthesis").as_posix()
            lines.append(
                f"- `{snapshot['id']}`：{snapshot['label']}，"
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


def render_summary_markdown(project: Path | str, model: dict | None = None) -> Path:
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


def build_synthesis_document(
    project: Path | str,
    model: dict | None = None,
    snapshot_id: str | None = None,
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
    if snapshot_id:
        snapshot = load_work_snapshot(project, snapshot_id)
        model = snapshot["model"]
    source = render_summary_markdown(project, model=model)
    from .render import render_html, write_document

    document = build_synthesis_document(project, model=model, snapshot_id=snapshot_id)
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
