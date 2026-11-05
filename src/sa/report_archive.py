"""Archive superseded report development versions without touching releases."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from .project import ProjectError, load_json
from .reporting import report_dir


ARCHIVE_SCHEMA = "sa.report-development-archive/1"
VERSION_RE = re.compile(r"^v(\d+)\.(\d+)$")
PREVIEW_DIR_RE = re.compile(r"^v(\d+)\.(\d+)(?:-r\d+)?$")
ARTIFACT_VERSION_RE = re.compile(r"-v(\d+)\.(\d+)(?:\.[^.]+)$")
PREVIEW_RETENTION = {"summary", "full", "none"}
SUMMARY_NAMES = {"all-slides-overview.jpg", "measurements.json"}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _parse_version(value: str, *, label: str = "版本") -> tuple[int, int]:
    match = VERSION_RE.fullmatch(value)
    if not match:
        raise ProjectError(f"{label}必须是 v<major>.<minor>，例如 v1.0")
    return int(match.group(1)), int(match.group(2))


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(project: Path, path: Path) -> str:
    return path.resolve().relative_to(project).as_posix()


def _assert_regular_file(path: Path, root: Path) -> None:
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ProjectError(f"归档文件越出报告目录：{path}")
    if path.is_symlink():
        raise ProjectError(f"归档不接受符号链接：{path}")


def _summary_entries(entries: list[tuple[Path, str]]) -> tuple[list[dict], int, int]:
    retained = []
    retained_bytes = 0
    for path, kind in entries:
        size = path.stat().st_size
        retained.append(
            {
                "path": path,
                "kind": kind,
                "bytes": size,
                "sha256": _digest_file(path),
            }
        )
        retained_bytes += size
    return retained, len(retained), retained_bytes


def _serialized_plan(project: Path, plan: dict) -> dict:
    value = {
        key: item
        for key, item in plan.items()
        if key not in {"artifacts", "previews", "retained_files"}
    }
    value["artifacts"] = [
        {
            "path": _relative(project, item["path"]),
            "version": item["version"],
            "bytes": item["bytes"],
        }
        for item in plan["artifacts"]
    ]
    value["previews"] = [
        {
            **{key: item for key, item in preview.items() if key not in {"path", "retained"}},
            "path": _relative(project, preview["path"]),
            "retained": [_relative(project, path) for path in preview["retained"]],
        }
        for preview in plan["previews"]
    ]
    value["retained_files"] = [
        {
            **{key: item for key, item in retained.items() if key != "path"},
            "path": _relative(project, retained["path"]),
        }
        for retained in plan["retained_files"]
    ]
    return value


def plan_report_archive(
    project: Path | str,
    report_id: str,
    before: str,
    *,
    preview_retention: str = "summary",
) -> dict:
    """Return a reviewable archive plan without modifying the project."""
    project_path = Path(project).resolve()
    cutoff = _parse_version(before)
    if preview_retention not in PREVIEW_RETENTION:
        raise ProjectError(f"preview-retention 必须是 {sorted(PREVIEW_RETENTION)}")
    root = report_dir(project_path, report_id)
    if not root.is_dir():
        raise ProjectError(f"报告不存在：{report_id}")
    project_meta = load_json(project_path / "project.json", {}) or {}
    project_id = project_meta.get("id")
    if not project_id:
        raise ProjectError("project.json 缺少项目 ID")
    artifacts_root = (root / "artifacts").resolve()
    previews_root = (root / "previews").resolve()

    artifacts: list[dict] = []
    if artifacts_root.is_dir():
        for path in sorted(artifacts_root.iterdir(), key=lambda item: item.name):
            if not path.is_file():
                continue
            match = ARTIFACT_VERSION_RE.search(path.name)
            if not match:
                continue
            version = (int(match.group(1)), int(match.group(2)))
            if version >= cutoff:
                continue
            _assert_regular_file(path, artifacts_root)
            artifacts.append(
                {
                    "path": path,
                    "version": f"v{version[0]}.{version[1]}",
                    "bytes": path.stat().st_size,
                }
            )

    artifact_versions = {item["version"] for item in artifacts}
    previews: list[dict] = []
    if previews_root.is_dir():
        for path in sorted(previews_root.iterdir(), key=lambda item: item.name):
            if not path.is_dir():
                continue
            match = PREVIEW_DIR_RE.fullmatch(path.name)
            if not match:
                continue
            version = (int(match.group(1)), int(match.group(2)))
            if version >= cutoff:
                continue
            preview_version = f"v{version[0]}.{version[1]}"
            if preview_version not in artifact_versions:
                raise ProjectError(
                    f"预览目录 {path.name} 缺少对应的旧版 PPTX，拒绝建立不可恢复归档"
                )
            files = []
            for item in sorted(path.rglob("*")):
                if item.is_symlink():
                    raise ProjectError(f"预览目录包含符号链接：{item}")
                if item.is_file():
                    files.append(item)
            if preview_retention == "full":
                retained = files
            elif preview_retention == "summary":
                retained = [item for item in files if item.name in SUMMARY_NAMES]
            else:
                retained = []
            omitted = [item for item in files if item not in retained]
            previews.append(
                {
                    "path": path,
                    "version": preview_version,
                    "files": len(files),
                    "bytes": sum(item.stat().st_size for item in files),
                    "retained": retained,
                    "retained_bytes": sum(item.stat().st_size for item in retained),
                    "omitted": len(omitted),
                    "omitted_bytes": sum(item.stat().st_size for item in omitted),
                }
            )

    retained_entries = [(item["path"], "artifact") for item in artifacts]
    for preview in previews:
        retained_entries.extend((path, "preview") for path in preview["retained"])
    retained_files, retained_count, retained_bytes = _summary_entries(retained_entries)
    versions = sorted({item["version"] for item in artifacts} | {item["version"] for item in previews})
    return {
        "schema": ARCHIVE_SCHEMA,
        "status": "planned",
        "project": project_id,
        "report": report_id,
        "before": before,
        "preview_retention": preview_retention,
        "versions": versions,
        "artifacts": artifacts,
        "previews": previews,
        "retained_files": retained_files,
        "totals": {
            "artifact_files": len(artifacts),
            "artifact_bytes": sum(item["bytes"] for item in artifacts),
            "preview_directories": len(previews),
            "preview_bytes": sum(item["bytes"] for item in previews),
            "retained_files": retained_count,
            "retained_bytes": retained_bytes,
            "omitted_files": sum(item["omitted"] for item in previews),
            "omitted_bytes": sum(item["omitted_bytes"] for item in previews),
        },
    }


def _verify_archive(
    path: Path,
    expected: dict[str, str],
    *,
    allow_extra: set[str] | None = None,
) -> None:
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise ProjectError(f"归档校验失败，损坏条目：{bad}")
        actual_names = {item.filename for item in archive.infolist() if not item.is_dir()}
        expected_names = set(expected) | (allow_extra or set())
        if actual_names != expected_names:
            missing = sorted(expected_names - actual_names)
            extra = sorted(actual_names - expected_names)
            raise ProjectError(f"归档条目不一致；缺失={missing}，额外={extra}")
        for name, digest in expected.items():
            value = hashlib.sha256()
            with archive.open(name) as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    value.update(chunk)
            if value.hexdigest() != digest:
                raise ProjectError(f"归档条目哈希不一致：{name}")


def verify_report_archive(
    project: Path | str,
    report_id: str,
    before: str,
) -> dict:
    """Verify an existing archive and its sidecar manifest."""
    project_path = Path(project).resolve()
    _parse_version(before)
    report_dir(project_path, report_id)
    archive_name = f"pre-{before}-development"
    archive_dir = project_path / "archive" / "reports" / report_id
    archive_path = archive_dir / f"{archive_name}.zip"
    manifest_path = archive_dir / f"{archive_name}.manifest.json"
    if not archive_path.is_file() or not manifest_path.is_file():
        raise ProjectError(f"归档不存在：{archive_name}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ProjectError(f"归档 manifest 不可读：{exc}") from exc
    if manifest.get("schema") != ARCHIVE_SCHEMA:
        raise ProjectError("归档 manifest schema 不受支持")
    if manifest.get("report") != report_id or manifest.get("before") != before:
        raise ProjectError("归档 manifest 与报告或 cutoff 不一致")
    if manifest.get("status") not in {"verified", "applied"}:
        raise ProjectError("归档 manifest 状态不是 verified/applied")
    archive_info = manifest.get("archive") or {}
    if archive_info.get("sha256") != _digest_file(archive_path):
        raise ProjectError("归档 ZIP 的 SHA-256 与 manifest 不一致")
    root_name = f"{report_id}-{archive_name}"
    expected = {}
    for item in manifest.get("retained_files", []):
        archive_entry = f"{root_name}/{item['path']}"
        expected[archive_entry] = item["sha256"]
    _verify_archive(
        archive_path,
        expected,
        allow_extra={f"{root_name}/archive-info.json"},
    )
    return manifest


def _remove_preview_dir(path: Path, previews_root: Path) -> None:
    resolved = path.resolve(strict=True)
    if resolved == previews_root or not resolved.is_relative_to(previews_root):
        raise ProjectError(f"拒绝删除越界预览目录：{path}")
    if path.is_symlink():
        raise ProjectError(f"拒绝删除符号链接：{path}")
    shutil.rmtree(path)


def create_report_archive(
    project: Path | str,
    report_id: str,
    before: str,
    *,
    preview_retention: str = "summary",
    apply: bool = False,
    keep_source: bool = False,
    force: bool = False,
) -> dict:
    """Create a version-stage archive; apply deletion only when requested."""
    project_path = Path(project).resolve()
    plan = plan_report_archive(
        project_path,
        report_id,
        before,
        preview_retention=preview_retention,
    )
    if not plan["retained_files"]:
        raise ProjectError(f"没有早于 {before} 的可归档报告产物")
    if not apply:
        return plan
    if keep_source and preview_retention != "full":
        # Keeping sources is compatible with any retention, but make the
        # consequence explicit in the manifest.
        pass

    root = report_dir(project_path, report_id)
    archive_dir = project_path / "archive" / "reports" / report_id
    archive_name = f"pre-{before}-development"
    archive_path = archive_dir / f"{archive_name}.zip"
    manifest_path = archive_dir / f"{archive_name}.manifest.json"
    if (archive_path.exists() or manifest_path.exists()) and not force:
        raise ProjectError(f"归档已存在：{archive_path.name}；确认替换时使用 --force")
    archive_dir.mkdir(parents=True, exist_ok=True)

    source_by_arcname = {
        f"{report_id}-{archive_name}/{_relative(project_path, item['path'])}": item["path"]
        for item in plan["retained_files"]
    }
    archive_info = {
        "schema": ARCHIVE_SCHEMA,
        "report": report_id,
        "before": before,
        "preview_retention": preview_retention,
        "files": [
            {
                "path": _relative(project_path, item["path"]),
                "kind": item["kind"],
                "bytes": item["bytes"],
                "sha256": item["sha256"],
            }
            for item in plan["retained_files"]
        ],
        "omission_policy": (
            "summary retains all-slides-overview.jpg and measurements.json; "
            "preview derivatives can be regenerated from archived PPTX files"
        ),
    }
    info_name = f"{report_id}-{archive_name}/archive-info.json"
    expected_hashes = {
        name: item["sha256"] for name, item in zip(source_by_arcname, plan["retained_files"])
    }
    info_bytes = (json.dumps(archive_info, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    expected_hashes[info_name] = hashlib.sha256(info_bytes).hexdigest()

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{archive_path.name}.",
            suffix=".tmp",
            dir=archive_dir,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
        with zipfile.ZipFile(
            temp_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            archive.writestr(info_name, info_bytes)
            for arcname, source in source_by_arcname.items():
                archive.write(source, arcname)
        _verify_archive(temp_path, expected_hashes)
        os.replace(temp_path, archive_path)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    manifest = {
        **_serialized_plan(project_path, plan),
        "status": "verified",
        "created_at": _now(),
        "archive": {
            "path": _relative(project_path, archive_path),
            "bytes": archive_path.stat().st_size,
            "sha256": _digest_file(archive_path),
        },
        "keep_source": keep_source,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if not keep_source:
        artifacts_root = (root / "artifacts").resolve()
        previews_root = (root / "previews").resolve()
        for item in plan["artifacts"]:
            path = item["path"]
            if path.resolve().parent != artifacts_root or path.is_symlink():
                raise ProjectError(f"拒绝删除越界产物：{path}")
            path.unlink()
        for item in plan["previews"]:
            _remove_preview_dir(item["path"], previews_root)
        manifest["status"] = "applied"

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest
