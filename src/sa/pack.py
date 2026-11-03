"""Explicit version packaging for Study Arca projects.

Packaging is intentionally separate from analysis, rendering and release
publication. A caller must select one immutable ``publish/vX.Y`` directory;
the archive is written only under ``publish/packed``.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import zipfile
from pathlib import Path

from .project import ProjectError


VERSION_RE = re.compile(r"^v\d+\.\d+$")


def _project_meta(project: Path) -> dict:
    path = project / "project.json"
    try:
        meta = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ProjectError(f"无法读取项目元信息 {path}: {exc}") from exc
    if not isinstance(meta, dict) or not isinstance(meta.get("id"), str):
        raise ProjectError("project.json 缺少有效项目 ID")
    return meta


def pack_release(project: Path | str, version: str, *, force: bool = False) -> Path:
    """Pack one published version directory into ``publish/packed``."""
    project = Path(project).resolve()
    if not VERSION_RE.fullmatch(version):
        raise ProjectError("版本必须是 v<major>.<minor>，例如 v1.0")

    meta = _project_meta(project)
    project_id = meta["id"]
    publish_root = (project / "publish").resolve()
    source = (publish_root / version).resolve()
    if not source.is_relative_to(publish_root) or not source.is_dir() or source.is_symlink():
        raise ProjectError(f"发布版本目录不存在或越出 publish：{version}")

    manifest_path = source / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ProjectError(f"发布版本缺少可读 manifest.json：{exc}") from exc
    if not isinstance(manifest, dict):
        raise ProjectError("发布 manifest 必须是 JSON 对象")
    if manifest.get("version") not in (None, version):
        raise ProjectError(
            f"发布 manifest 版本 {manifest.get('version')!r} 与目录 {version!r} 不一致"
        )

    files: list[tuple[Path, str]] = []
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ProjectError(f"发布目录不得包含符号链接：{path.relative_to(source)}")
        if not path.is_file():
            continue
        resolved = path.resolve()
        if not resolved.is_relative_to(source):
            raise ProjectError(f"发布目录包含越界文件：{path}")
        files.append((path, path.relative_to(source).as_posix()))
    if not files:
        raise ProjectError(f"发布版本为空：{source}")

    packed = publish_root / "packed"
    packed.mkdir(parents=True, exist_ok=True)
    target = packed / f"{project_id}-{version}.zip"
    if target.exists() and not force:
        raise ProjectError(f"打包文件已存在：{target.name}；确认替换时使用 --force")

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{target.name}.", suffix=".tmp", dir=packed, delete=False
        ) as handle:
            temp_path = Path(handle.name)
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, relative in files:
                archive.write(path, f"{project_id}-{version}/{relative}")
        os.replace(temp_path, target)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return target
