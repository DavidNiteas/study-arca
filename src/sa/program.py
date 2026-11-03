"""Thin, fact-free program repositories built on Git submodules."""
from __future__ import annotations

import json
import os
import posixpath
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from .project import ProjectError, load_json, save_json


SCHEMA = "sa.program/1"
PROGRAM_ID_RE = re.compile(r"^(?:work-root|prog-[a-z0-9][a-z0-9-]*)$")
DISTRIBUTIONS = {"local", "cloneable"}
LOCAL_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/|\.{1,2}[\\/]|file:)")


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    command = ["git", "-C", str(root), *args]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and result.returncode != 0:
        raise ProjectError(result.stderr.strip() or f"git 命令失败：{' '.join(args)}")
    return result


def load_program(program: Path | str) -> dict:
    program = Path(program).resolve()
    data = load_json(program / "program.json", None)
    if not isinstance(data, dict):
        raise ProjectError(f"不是 program 目录：{program}")
    errors = validate_program_meta(data)
    if errors:
        raise ProjectError("\n".join(errors))
    return data


def validate_program_meta(data: dict) -> list[str]:
    errors: list[str] = []
    if data.get("schema") != SCHEMA:
        errors.append(f"program.json schema 必须是 {SCHEMA}")
    if not isinstance(data.get("id"), str) or not PROGRAM_ID_RE.fullmatch(data["id"]):
        errors.append("program id 必须以 prog- 开头，或为 work-root")
    if not isinstance(data.get("title"), str) or not data["title"].strip():
        errors.append("program title 不能为空")
    if data.get("status") not in {"active", "suspended", "archived"}:
        errors.append("program status 必须是 active/suspended/archived")
    if data.get("distribution") not in DISTRIBUTIONS:
        errors.append("program distribution 必须是 local/cloneable")
    return errors


def init_program(
    path: Path | str,
    program_id: str,
    title: str,
    *,
    git: bool = True,
    allow_existing: bool = False,
) -> Path:
    path = Path(path).resolve()
    if path.exists() and any(path.iterdir()) and not allow_existing:
        raise ProjectError(f"目标目录非空：{path}")
    if (path / "program.json").exists():
        raise ProjectError(f"program 已初始化：{path}")
    if not PROGRAM_ID_RE.fullmatch(program_id):
        raise ProjectError("program id 必须以 prog- 开头，或为 work-root")
    if not title.strip():
        raise ProjectError("program title 不能为空")
    path.mkdir(parents=True, exist_ok=True)
    save_json(path / "program.json", {
        "schema": SCHEMA,
        "id": program_id,
        "title": title.strip(),
        "status": "active",
        "distribution": "local",
    })
    (path / "nodes").mkdir(exist_ok=True)
    if not any((path / "nodes").iterdir()):
        (path / "nodes" / ".gitkeep").touch()
    ignore = path / ".gitignore"
    if not ignore.exists():
        ignore.write_text(
            "index.json\n*.tmp\n*.log\n.DS_Store\nThumbs.db\n",
            encoding="utf-8",
        )
    template_bin = Path(__file__).resolve().parents[2] / "templates" / "program" / "bin"
    if template_bin.is_dir():
        shutil.copytree(template_bin, path / "bin")
    if git and shutil.which("git"):
        result = subprocess.run(
            ["git", "init", "-q"],
            cwd=path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise ProjectError(result.stderr.strip() or "git init 失败")
    return path


def _node_manifest(path: Path) -> tuple[str, str]:
    project = load_json(path / "project.json", None)
    if isinstance(project, dict):
        node_id = project.get("id")
        node_type = project.get("workspace_type") or "research"
        if isinstance(node_id, str) and node_id:
            from .workspace import SCHEMA as WORKSPACE_SCHEMA, WORKFLOW_BY_TYPE
            if project.get("schema") == WORKSPACE_SCHEMA:
                if node_type not in WORKFLOW_BY_TYPE:
                    raise ProjectError(f"子 workspace 类型非法：{node_type}")
                if project.get("workflow") != WORKFLOW_BY_TYPE[node_type]:
                    raise ProjectError(f"子 workspace workflow 与类型不一致：{node_id}")
            return node_id, node_type
    program = load_json(path / "program.json", None)
    if isinstance(program, dict) and program.get("schema") == SCHEMA:
        errors = validate_program_meta(program)
        if errors:
            raise ProjectError("\n".join(errors))
        node_id = program.get("id")
        if isinstance(node_id, str) and node_id:
            return node_id, "program"
    raise ProjectError(f"子节点缺少有效 project.json 或 program.json：{path}")


def _submodule_entries(program: Path) -> dict[str, dict[str, str]]:
    config = program / ".gitmodules"
    if not config.is_file():
        return {}
    result = _git(program, "config", "-f", ".gitmodules", "--get-regexp", r"^submodule\..*\.(path|url)$")
    entries: dict[str, dict[str, str]] = {}
    for line in result.stdout.splitlines():
        if " " not in line:
            continue
        key, value = line.split(" ", 1)
        match = re.fullmatch(r"submodule\.(.+)\.(path|url)", key)
        if not match:
            continue
        name, field = match.groups()
        entries.setdefault(name, {})[field] = value
    return entries


def _gitlinks(program: Path) -> set[str]:
    result = _git(program, "ls-files", "--stage", "-z", check=False)
    paths: set[str] = set()
    for record in result.stdout.split("\0"):
        if not record or "\t" not in record:
            continue
        info, path = record.split("\t", 1)
        parts = info.split()
        if parts and parts[0] == "160000":
            paths.add(path)
    return paths


def attach_node(program: Path | str, source: Path | str, node_path: str | None = None) -> Path:
    program = Path(program).resolve()
    source = Path(source).resolve()
    load_program(program)
    node_id, _ = _node_manifest(source)
    relative = node_path or f"nodes/{node_id}"
    target = (program / relative).resolve()
    if not target.is_relative_to(program) or not target.is_relative_to((program / "nodes").resolve()):
        raise ProjectError("子节点路径必须位于 program/nodes")
    existing = target.exists() and target.resolve() == source
    if target.exists() and not existing:
        raise ProjectError(f"子节点路径已存在：{relative}")
    if _git(source, "rev-parse", "--show-toplevel", check=False).returncode != 0:
        raise ProjectError("被挂载节点必须是已初始化的 Git 仓库")
    if existing:
        commit = _git(source, "rev-parse", "HEAD").stdout.strip()
        origin = _git(source, "remote", "get-url", "origin", check=False)
        url = origin.stdout.strip() if origin.returncode == 0 and origin.stdout.strip() else str(source)
        _git(program, "config", "-f", ".gitmodules", f"submodule.{node_id}.path", relative)
        _git(program, "config", "-f", ".gitmodules", f"submodule.{node_id}.url", url)
        _git(program, "add", ".gitmodules")
        _git(program, "update-index", "--add", "--cacheinfo", f"160000,{commit},{relative}")
        _git(program, "submodule", "init", "--", relative)
    else:
        result = subprocess.run(
            ["git", "-c", "protocol.file.allow=always", "-C", str(program),
             "submodule", "add", str(source), relative],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise ProjectError(result.stderr.strip() or "git submodule add 失败")
    keep = program / "nodes" / ".gitkeep"
    if keep.exists() and any(path != keep for path in (program / "nodes").iterdir()):
        keep.unlink()
    return target


def program_status(program: Path | str) -> dict:
    program = Path(program).resolve()
    meta = load_program(program)
    result = _git(program, "submodule", "status", "--recursive", check=False)
    submodules = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        flag, rest = line[0], line[1:]
        parts = rest.split()
        if len(parts) < 2:
            continue
        child = program / parts[1]
        dirty = bool(
            child.is_dir()
            and _git(child, "status", "--porcelain", "--untracked-files=all", check=False).stdout.strip()
        )
        submodules.append({
            "flag": flag,
            "commit": parts[0],
            "path": parts[1],
            "dirty": dirty,
        })
    entry_paths = {fields.get("path") for fields in _submodule_entries(program).values()}
    orphan_gitlinks = sorted(_gitlinks(program) - entry_paths)
    return {
        **meta,
        "submodules": submodules,
        "orphan_gitlinks": orphan_gitlinks,
        "submodules_dirty": any(item["flag"] != " " or item["dirty"] for item in submodules),
        "working_tree_dirty": bool(_git_status(program, ignore_submodules_all=True)),
    }


def _portable_remote_url(url: str) -> bool:
    if not url or LOCAL_PATH_RE.match(url) or re.match(r"^[A-Za-z]:", url):
        return False
    return bool(
        re.match(r"^(?:https?|ssh|git)://", url)
        or re.match(r"^[^/@\s]+@[^:\s]+:.+", url)
    )


def _resolve_remote_url(base_url: str, url: str) -> str:
    if _portable_remote_url(url):
        return url
    if base_url.startswith(("http://", "https://", "ssh://", "git://")):
        return urljoin(base_url.rstrip("/") + "/", url)
    match = re.match(r"^(?P<prefix>[^/@\s]+@[^:\s]+):(?P<path>.+)$", base_url)
    if match:
        base_path = match.group("path")
        return (
            f"{match.group('prefix')}:"
            f"{posixpath.normpath(posixpath.join(base_path, url))}"
        )
    raise ProjectError(f"无法解析相对远端 URL：{url}")


def _remote_has_commit(url: str, commit: str, *, cwd: Path) -> tuple[bool, str]:
    listed = subprocess.run(
        ["git", "ls-remote", url],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if listed.returncode != 0:
        return False, "远端不可访问"
    if any(line.split()[0] == commit for line in listed.stdout.splitlines() if line.split()):
        return True, ""
    with tempfile.TemporaryDirectory(prefix="sa-program-preflight-") as tmp:
        _git(Path(tmp), "init", "--bare", "-q")
        fetched = subprocess.run(
            ["git", "-C", str(tmp), "fetch", "--no-tags", url, commit],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if fetched.returncode != 0:
            return False, "pin 提交不可取得"
        exists = _git(Path(tmp), "cat-file", "-e", f"{commit}^{{commit}}", check=False)
        if exists.returncode != 0:
            return False, "pin 提交对象无效"
    return True, ""


def check_program(
    program: Path | str,
    *,
    require_cloneable: bool = False,
    _visited: set[Path] | None = None,
    _seen_ids: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    program = Path(program).resolve()
    visited = _visited if _visited is not None else set()
    seen_ids = _seen_ids if _seen_ids is not None else set()
    if program in visited:
        return ["program 引用树出现循环"], []
    visited.add(program)
    errors: list[str] = []
    warnings: list[str] = []
    try:
        meta = load_program(program)
    except ProjectError as exc:
        return [str(exc)], warnings
    if meta["id"] in seen_ids:
        errors.append(f"program 树中出现重复节点 ID：{meta['id']}")
    seen_ids.add(meta["id"])
    if _git(program, "rev-parse", "--show-toplevel", check=False).returncode != 0:
        errors.append("program 不是 Git 仓库")
        return errors, warnings
    origin_url: str | None = None
    if require_cloneable:
        origin = _git(program, "remote", "get-url", "origin", check=False)
        if origin.returncode != 0 or not origin.stdout.strip():
            errors.append("cloneable program 必须配置 origin 远端")
        else:
            origin_url = origin.stdout.strip()
            if not _portable_remote_url(origin_url):
                errors.append(f"cloneable program origin 不是可移植远端：{origin_url}")
            head = _git(program, "rev-parse", "HEAD", check=False)
            if head.returncode != 0 or not head.stdout.strip():
                errors.append("cloneable program 尚无 HEAD 提交")
            else:
                reachable, reason = _remote_has_commit(origin_url, head.stdout.strip(), cwd=program)
                if not reachable:
                    errors.append(f"program 根 {reason}：{origin_url}@{head.stdout.strip()}")
    root_dirty = bool(_git_status(program, ignore_submodules_all=True))
    if root_dirty:
        if require_cloneable:
            errors.append("cloneable program 根工作树必须干净")
        else:
            warnings.append("program 根工作树有未提交修改")
    entries = _submodule_entries(program)
    entry_paths = {fields.get("path") for fields in entries.values() if fields.get("path")}
    for path in sorted(_gitlinks(program) - entry_paths):
        errors.append(f"存在未登记 .gitmodules 的 gitlink：{path}")
    for path in sorted(entry_paths - _gitlinks(program)):
        errors.append(f".gitmodules 条目缺少 gitlink：{path}")
    status = program_status(program)
    by_path = {item["path"]: item for item in status["submodules"]}
    for name, fields in entries.items():
        relative = fields.get("path")
        url = fields.get("url")
        if not relative:
            errors.append(f"submodule {name} 缺少 path")
            continue
        if not relative.startswith("nodes/"):
            errors.append(f"submodule {name} 路径必须位于 nodes/：{relative}")
        state = by_path.get(relative)
        if state is None:
            errors.append(f"submodule {name} 未出现在 git submodule status：{relative}")
            continue
        if state["flag"] in {"-", "U"}:
            errors.append(f"submodule {name} 未初始化或冲突：{state['flag']}")
            continue
        if state["flag"] == "+":
            warnings.append(f"submodule {name} HEAD 与 program pin 不一致")
        if state.get("dirty"):
            warnings.append(f"submodule {name} 有未提交修改；program 版本只固定其 HEAD")
        child = program / relative
        try:
            node_id, node_type = _node_manifest(child)
        except ProjectError as exc:
            errors.append(str(exc))
            continue
        if node_type == "program":
            child_meta = load_json(child / "program.json", {}) or {}
            if require_cloneable and child_meta.get("distribution") != "cloneable":
                errors.append(f"子 program {node_id} 不是 cloneable")
            child_errors, child_warnings = check_program(
                child,
                require_cloneable=require_cloneable,
                _visited=visited,
                _seen_ids=seen_ids,
            )
            errors.extend(f"{node_id}: {message}" for message in child_errors)
            warnings.extend(f"{node_id}: {message}" for message in child_warnings)
        else:
            if node_id in seen_ids:
                errors.append(f"program 树中出现重复节点 ID：{node_id}")
            seen_ids.add(node_id)
        if require_cloneable:
            if not url:
                errors.append(f"submodule {name} 缺少 clone URL")
            else:
                try:
                    child_url = _resolve_remote_url(origin_url or "", url)
                except ProjectError as exc:
                    errors.append(f"submodule {name}: {exc}")
                else:
                    if not _portable_remote_url(child_url):
                        errors.append(f"submodule {name} URL 不是可移植远端：{child_url}")
                    else:
                        reachable, reason = _remote_has_commit(
                            child_url,
                            state["commit"],
                            cwd=program,
                        )
                        if not reachable:
                            errors.append(
                                f"submodule {name} {reason}：{child_url}@{state['commit']}"
                            )
    return errors, warnings


def set_distribution(program: Path | str, distribution: str) -> dict:
    program = Path(program).resolve()
    if distribution not in DISTRIBUTIONS:
        raise ProjectError("distribution 必须是 local/cloneable")
    if distribution == "cloneable":
        errors, _ = check_program(program, require_cloneable=True)
        if errors:
            raise ProjectError("\n".join(errors))
    meta = load_program(program)
    meta["distribution"] = distribution
    save_json(program / "program.json", meta)
    return meta


def _git_status(program: Path, *, ignore_submodules_all: bool = False) -> str:
    args = ["status", "--porcelain", "--untracked-files=all"]
    args.append("--ignore-submodules=all" if ignore_submodules_all else "--ignore-submodules=none")
    result = _git(program, *args, check=False)
    return result.stdout.strip()


def clone_program(source: str, destination: Path | str, *, verify_cloneable: bool = True) -> Path:
    destination = Path(destination).resolve()
    if destination.exists():
        raise ProjectError(f"目标目录已存在：{destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=".sa-program-clone-", dir=destination.parent))
    checkout = temp_root / "program"
    try:
        result = subprocess.run(
            [
                "git",
                "-c",
                "protocol.file.allow=always",
                "clone",
                "--recurse-submodules",
                source,
                str(checkout),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise ProjectError(result.stderr.strip() or "program clone 失败")
        meta = load_program(checkout)
        if verify_cloneable and meta.get("distribution") != "cloneable":
            raise ProjectError("来源 program 未标记为 cloneable")
        errors, _ = check_program(
            checkout,
            require_cloneable=verify_cloneable,
        )
        if errors:
            raise ProjectError("\n".join(errors))
        checkout.rename(destination)
        return destination
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def bundle_program(program: Path | str, output: Path | str, *, force: bool = False) -> Path:
    program = Path(program).resolve()
    output = Path(output).resolve()
    if output.exists() and not force:
        raise ProjectError(f"迁移包已存在：{output}；确认替换时使用 --force")
    meta = load_program(program)
    if _git_status(program):
        raise ProjectError("program 工作树不干净；提交后或清理后再生成迁移包")
    errors, warnings = check_program(program)
    if errors or warnings:
        raise ProjectError("\n".join(errors + warnings))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sa-program-bundle-", dir=output.parent) as tmp:
        snapshot = clone_program(str(program), Path(tmp) / "snapshot", verify_cloneable=False)
        temp_zip = Path(tmp) / "bundle.zip"
        files = []
        for root, dirs, names in os.walk(snapshot, followlinks=False):
            root_path = Path(root)
            for name in dirs + names:
                path = root_path / name
                if path.is_symlink():
                    raise ProjectError(f"program bundle 拒绝符号链接：{path.relative_to(snapshot)}")
            files.extend(root_path / name for name in names)
        with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(files):
                if path.is_file():
                    relative = path.relative_to(snapshot).as_posix()
                    archive.write(path, f"{meta['id']}/{relative}")
        os.replace(temp_zip, output)
    return output


def program_index(program: Path | str) -> dict:
    status = program_status(program)
    errors, warnings = check_program(program)
    return {
        "schema": "sa.program-index/1",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "program": status["id"],
        "distribution": status["distribution"],
        "nodes": status["submodules"],
        "errors": errors,
        "warnings": warnings,
    }
