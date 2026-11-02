"""Append-only output registry for independent DOCX, HTML and PPT pipelines.

The research cycle records process and Research Snapshots. This registry records
output-specific requests, plans, layouts, rendered artifacts, previews and
review events without changing the sa.research/1 schema.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .cycle import load_cycle
from .project import ProjectError, load_json, save_json
from .research_ir import validate_research_ir

SCHEMA = "sa.outputs/1"
RECORD_TYPES = {"output", "review"}
FORMATS = {"docx", "html", "pptx"}
PLAN_SCHEMAS = {
    "docx": "sa.document-plan/1",
    "html": "sa.experience-plan/1",
    "pptx": "sa.deck-plan/1",
}
ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,79}$")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _artifact_index(project: Path) -> dict[str, dict]:
    cycle = load_cycle(project)
    return {
        record["id"]: record
        for record in cycle["records"]
        if record.get("type") == "artifact"
    }


def _artifact_path(project: Path, artifact: dict) -> Path:
    path = (project / artifact["path"]).resolve()
    if not path.is_relative_to(project) or not path.is_file():
        raise ProjectError(f"artifact 文件不存在或越出项目：{artifact['path']}")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != artifact["sha256"]:
        raise ProjectError(f"artifact 哈希不一致：{artifact['id']}")
    return path


def _json_artifact(project: Path, artifacts: dict[str, dict], artifact_id: str, kind: str) -> dict:
    if artifact_id not in artifacts:
        raise ProjectError(f"{kind} 不是已冻结 artifact：{artifact_id}")
    path = _artifact_path(project, artifacts[artifact_id])
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ProjectError(f"{kind} artifact 不是有效 JSON：{artifact_id}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProjectError(f"{kind} artifact 必须是 JSON 对象：{artifact_id}")
    return value


def _validate_output(project: Path, record: dict, artifacts: dict[str, dict], seen: dict[str, dict]) -> list[str]:
    errors: list[str] = []
    output_id = record["id"]
    output_format = record.get("format")
    if output_format not in FORMATS:
        return [f"{output_id}.format 必须是 {sorted(FORMATS)}"]
    for field in ("agreement", "round", "snapshot", "request", "plan", "artifact", "renderer"):
        if not isinstance(record.get(field), str) or not record[field].strip():
            errors.append(f"{output_id}.{field} 必须是非空字符串或引用")
    if errors:
        return errors

    cycle = load_cycle(project)
    index = {item["id"]: item for item in cycle["records"]}
    agreement = index.get(record["agreement"])
    round_record = index.get(record["round"])
    if not agreement or agreement.get("type") != "agreement" or agreement.get("status") != "approved":
        errors.append(f"{output_id}.agreement 不是已批准约定")
    if not round_record or round_record.get("type") != "round":
        errors.append(f"{output_id}.round 不是研究轮次")
    elif round_record.get("agreement") != record["agreement"]:
        errors.append(f"{output_id} 的 agreement 与 round 不一致")

    for field in ("snapshot", "request", "plan", "layout", "artifact", "preview"):
        value = record.get(field)
        if value is not None and value not in artifacts:
            errors.append(f"{output_id}.{field} 不是已冻结 artifact：{value}")
    if output_format == "pptx" and not record.get("layout"):
        errors.append(f"{output_id}.layout 在 pptx 输出中必需")
    if errors:
        return errors

    try:
        snapshot = _json_artifact(project, artifacts, record["snapshot"], "snapshot")
        if snapshot.get("schema") != "sa.research-ir/1":
            errors.append(f"{output_id}.snapshot schema 不是 sa.research-ir/1")
        else:
            errors.extend(
                f"{output_id}.snapshot: {error}"
                for error in validate_research_ir(project, snapshot, verify_sources=False)
            )

        request = _json_artifact(project, artifacts, record["request"], "request")
        if request.get("schema") != "sa.output-request/1":
            errors.append(f"{output_id}.request schema 不是 sa.output-request/1")
        if request.get("format") != output_format:
            errors.append(f"{output_id}.request format 与输出不一致")
        if request.get("snapshot") != record["snapshot"]:
            errors.append(f"{output_id}.request snapshot 与输出不一致")

        plan = _json_artifact(project, artifacts, record["plan"], "plan")
        expected_schema = PLAN_SCHEMAS[output_format]
        if plan.get("schema") != expected_schema:
            errors.append(f"{output_id}.plan schema 必须是 {expected_schema}")
        if plan.get("format") != output_format:
            errors.append(f"{output_id}.plan format 与输出不一致")
        if plan.get("snapshot") != record["snapshot"]:
            errors.append(f"{output_id}.plan snapshot 与输出不一致")

        if record.get("layout"):
            layout = _json_artifact(project, artifacts, record["layout"], "layout")
            if layout.get("schema") != "sa.render-layout/1":
                errors.append(f"{output_id}.layout schema 必须是 sa.render-layout/1")
            if layout.get("plan") != record["plan"]:
                errors.append(f"{output_id}.layout plan 与输出不一致")
    except ProjectError as exc:
        errors.append(f"{output_id}: {exc}")
    return errors


def validate_registry(project: Path | str, data: dict) -> list[str]:
    project = Path(project).resolve()
    errors: list[str] = []
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return ["未知输出登记 schema"]
    meta = load_json(project / "project.json", {}) or {}
    if data.get("project") != meta.get("id"):
        errors.append("输出登记 project 与 project.json 不一致")
    records = data.get("records")
    if not isinstance(records, list):
        return errors + ["records 必须是数组"]
    artifacts = _artifact_index(project)
    seen: dict[str, dict] = {}
    outputs: dict[str, dict] = {}
    for number, record in enumerate(records):
        mark = f"records[{number}]"
        if not isinstance(record, dict):
            errors.append(mark + " 必须是对象")
            continue
        record_id = record.get("id")
        kind = record.get("type")
        if not isinstance(record_id, str) or not ID_RE.fullmatch(record_id) or record_id in seen:
            errors.append(mark + " id 非法或重复")
            continue
        if kind not in RECORD_TYPES:
            errors.append(f"{record_id}.type 非法")
            continue
        try:
            timestamp = datetime.fromisoformat(record.get("at", ""))
            if timestamp.tzinfo is None:
                raise ValueError()
        except (TypeError, ValueError):
            errors.append(f"{record_id}.at 必须是带时区 ISO 时间")
        if kind == "output":
            errors.extend(_validate_output(project, record, artifacts, seen))
            outputs[record_id] = record
        else:
            output_id = record.get("output")
            if output_id not in outputs:
                errors.append(f"{record_id}.output 必须引用前序 output")
            status = record.get("status")
            if status not in ("pending", "passed", "failed"):
                errors.append(f"{record_id}.status 非法")
            elif status in ("passed", "failed"):
                output = outputs.get(output_id, {})
                if not output.get("preview"):
                    errors.append(f"{record_id} 需要 output.preview")
                if record.get("reviewed") is not True:
                    errors.append(f"{record_id}.reviewed 必须为 true")
                if record.get("mode") not in ("self", "independent"):
                    errors.append(f"{record_id}.mode 非法")
                if not isinstance(record.get("reviewer"), str) or not record["reviewer"].strip():
                    errors.append(f"{record_id}.reviewer 必须是非空文本")
                if not isinstance(record.get("notes"), str) or not record["notes"].strip():
                    errors.append(f"{record_id}.notes 必须是非空文本")
        seen[record_id] = record
    return errors


def registry_path(project: Path | str) -> Path:
    return Path(project) / "outputs/registry.json"


def load_registry(project: Path | str) -> dict:
    data = load_json(registry_path(project), None)
    if data is None:
        raise ProjectError("输出登记不存在；先运行 sa output init")
    errors = validate_registry(project, data)
    if errors:
        raise ProjectError("\n".join(errors))
    return data


@contextmanager
def writer(project: Path | str):
    directory = Path(project) / "outputs"
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / ".output.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise ProjectError("输出登记正被写入；确认无写者后再处理锁") from exc
    try:
        with handle:
            handle.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)


def init_registry(project: Path | str) -> Path:
    project = Path(project).resolve()
    meta = load_json(project / "project.json", {}) or {}
    if not meta.get("id"):
        raise ProjectError("不是有效项目目录")
    path = registry_path(project)
    if path.exists():
        load_registry(project)
        return path
    with writer(project):
        save_json(path, {"schema": SCHEMA, "project": meta["id"], "records": []})
        readme = project / "outputs/README.md"
        if not readme.exists():
            readme.write_text(
                "# 输出登记\n\n本目录按 `sa.outputs/1` 追加记录 DOCX、HTML、PPT 输出。\n"
                "记录只引用冻结 artifact，不复制事实台账。使用 `sa output status/lint` 查看。\n",
                encoding="utf-8",
            )
    return path


def apply_records(project: Path | str, records) -> int:
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list) or not records:
        raise ProjectError("输入必须是非空记录数组或单条记录")
    project = Path(project).resolve()
    with writer(project):
        data = load_registry(project)
        for value in records:
            record = copy.deepcopy(value)
            if not isinstance(record, dict):
                raise ProjectError("每条记录必须是对象")
            record.setdefault("at", _now())
            data["records"].append(record)
        errors = validate_registry(project, data)
        if errors:
            raise ProjectError("\n".join(errors))
        save_json(registry_path(project), data)
    return len(records)


def output_status(project: Path | str) -> dict:
    data = load_registry(project)
    records = data["records"]
    reviews: dict[str, dict] = {}
    for record in records:
        if record["type"] == "review":
            reviews[record["output"]] = record
    outputs = []
    for record in records:
        if record["type"] != "output":
            continue
        review = reviews.get(record["id"])
        outputs.append({
            "id": record["id"],
            "format": record["format"],
            "snapshot": record["snapshot"],
            "artifact": record["artifact"],
            "preview": record.get("preview"),
            "review": review.get("status") if review else "pending",
        })
    return {
        "schema": SCHEMA,
        "project": data["project"],
        "outputs": outputs,
        "records": len(records),
    }

