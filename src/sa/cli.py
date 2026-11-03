"""sa 命令行入口（脚本 scripts/sa.py 只做转发）。"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from . import __version__
from .evidence import lint_project
from .docx_render import DOCX_AVAILABLE, RenderDependencyError, render_docx
from .dialect import dialect_status, import_dialect, init_user_dialect, promote_dialect
from .pack import pack_release
from .program import (
    attach_node,
    bundle_program,
    check_program,
    clone_program,
    init_program,
    program_index,
    program_status,
    set_distribution,
)
from .render import build_document, render_html, write_document
from .synthesis import (
    build_synthesis_report,
    init_synthesis,
    validate_synthesis,
)
from .project import (
    EVIDENCE_GRADES,
    ProjectError,
    add_source,
    add_sources_batch,
    new_project,
    status_counts,
)
from .workspace import (
    PROVIDED_AUTHORITY,
    PROVIDED_ROLES,
    PROVIDED_VERIFICATION,
    REFERENCE_RELATIONS,
    WORK_ORDER_STATUS,
    WORKSPACE_TYPES,
    add_provided_input,
    add_reference,
    create_work_order,
    load_work_orders,
    set_work_order_status,
    validate_references,
    verify_reference_authorities,
    workspace_status,
)


def _print_report(report, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(
            {"errors": report.errors, "warnings": report.warnings, "infos": report.infos},
            ensure_ascii=False,
            indent=2,
        ))
        return
    for message in report.errors:
        print(f"[ERROR] {message}")
    for message in report.warnings:
        print(f"[WARN ] {message}")
    for message in report.infos:
        print(f"[INFO ] {message}")
    print(
        f"\n汇总：{len(report.errors)} error / {len(report.warnings)} warn / "
        f"{len(report.infos)} info"
    )


def cmd_new(args) -> int:
    dest = new_project(
        args.slug,
        args.title,
        args.root,
        args.date,
        workflow=args.workflow,
        workspace_type=args.workspace_type,
    )
    print(f"已创建：{dest}")
    print(f"工作区类型：{args.workspace_type}")
    print(f"独立仓库：{'已初始化' if (dest / '.git').exists() else '未初始化（检查 git）'}")
    print("\n下一步：")
    if args.workspace_type == "research" and args.workflow == "cycle":
        print("  1. 填 brief/brief.md，按 docs/09 登记研究约定，再建立问题与轮次")
        print(f'     python scripts/sa.py cycle status "{dest}"')
    elif args.workspace_type == "synthesis":
        print("  1. 填 brief/brief.md 和 brief/provided/manifest.json，再登记工作对象")
        print(f'     python scripts/sa.py work new "{dest}" --title ... --goal ...')
    else:
        print(f"  1. 填 {dest / 'brief' / 'brief.md'} 与 _dev/01-目标与设计.md（G0）")
    print(f"  2. 采集后建信封：python scripts/sa.py source \"{dest}\" --title ...")
    print(f"  3. 校验：python scripts/sa.py lint \"{dest}\"")
    return 0


def cmd_pack(args) -> int:
    output = pack_release(Path(args.project), args.version, force=args.force)
    print(f"已打包：{output}")
    return 0


def cmd_dialect(args) -> int:
    if args.action == "init":
        from .project import REPO_ROOT
        print(f"已初始化用户方言：{init_user_dialect(REPO_ROOT)}")
        return 0
    if args.action == "status":
        from .project import REPO_ROOT
        print(json.dumps(
            dialect_status(REPO_ROOT, args.workspace),
            ensure_ascii=False,
            indent=2,
        ))
        return 0
    if args.action == "import":
        if not args.workspace or not args.source:
            raise ProjectError("dialect import 需要 --workspace 和 --source")
        print(f"已导入工作区方言：{import_dialect(args.workspace, args.source)}")
        return 0
    if args.action == "promote":
        if not args.workspace or not args.scope:
            raise ProjectError("dialect promote 需要 --workspace 和 --scope")
        from .project import REPO_ROOT
        promoted = promote_dialect(
            REPO_ROOT,
            args.workspace,
            scope=args.scope,
            output=args.output,
        )
        print(f"已生成方言晋升结果：{promoted}")
        return 0
    raise ProjectError(f"未知 dialect 操作：{args.action}")


def cmd_source(args) -> int:
    if args.batch:
        batch_path = Path(args.batch)
        if not batch_path.exists():
            print(f"[ERROR] 找不到批量文件：{batch_path}", file=sys.stderr)
            return 2
        try:
            payload = json.loads(batch_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"[ERROR] 批量文件不是合法 JSON：{exc}", file=sys.stderr)
            return 2
        items = payload.get("sources") if isinstance(payload, dict) else payload
        created = add_sources_batch(Path(args.project), items)
        print(f"已建 {len(created)} 条来源：")
        for path in created:
            print(f"  {path.name}")
        return 0

    required = {
        "--title": args.title,
        "--tool": args.tool,
        "--locator": args.locator,
        "--publisher": args.publisher,
    }
    missing = [flag for flag, value in required.items() if not value]
    if missing:
        print(f"[ERROR] 缺少参数：{', '.join(missing)}（或用 --batch）", file=sys.stderr)
        return 2

    dest = add_source(
        Path(args.project),
        title=args.title,
        tool=args.tool,
        locator=args.locator,
        publisher=args.publisher,
        grade=args.grade,
        query=args.query,
        source_type=args.type,
        license_text=args.license,
        notes=args.notes,
        slug=args.slug,
    )
    print(f"已建来源：{dest}")
    print("请补充 extracted.md 的摘录与口径，并把原始文件放入 raw/。")
    return 0


def cmd_lint(args) -> int:
    report = lint_project(
        Path(args.project),
        stale_days=args.stale_days,
        report_path=args.report,
    )
    _print_report(report, args.json)
    if report.errors:
        return 1
    if args.strict and report.warnings:
        return 1
    return 0


def cmd_status(args) -> int:
    counts = status_counts(Path(args.project))
    counts["workspace"] = workspace_status(Path(args.project))
    cycle = None
    if (Path(args.project) / "research/cycle.json").exists():
        from .cycle import cycle_status
        cycle = cycle_status(Path(args.project))
        counts["research_cycle"] = cycle
    if args.json:
        print(json.dumps(counts, ensure_ascii=False, indent=2))
        return 0
    print(f"项目：{counts['id']}  {counts['title']}")
    print(f"工作区类型：{counts['workspace'].get('workspace_type') or 'legacy'}")
    print(f"状态：{counts['status']}")
    print(f"工单：{counts['workspace']['work_orders']} "
          f"(待处理 {counts['workspace']['work_orders_open']})")
    print(f"用户材料：{counts['workspace']['provided_inputs']}  "
          f"引用：{counts['workspace']['references']}")
    if counts["workspace"].get("workspace_type") == "research":
        print(f"来源：{counts['sources']}  "
              f"(E1={counts['grades']['E1']} E2={counts['grades']['E2']} "
              f"E3={counts['grades']['E3']} E4={counts['grades']['E4']})")
        print(f"结论：{counts['claims']}  "
              f"(high={counts['confidence']['high']} "
              f"medium={counts['confidence']['medium']} low={counts['confidence']['low']})")
        print(f"基准事实：{counts['facts']}  冲突：{counts['conflicts']} "
              f"(未决 {counts['conflicts_unresolved']})")
    if cycle is not None:
        print(f"研究循环：{len(cycle['rounds'])} 轮；{sum(a['status'] == 'open' for a in cycle['actions'])} 个待处理任务；当前约定 {cycle['current_agreement']}")
    if counts.get("waivers"):
        print(f"Gate waiver：{counts['waivers']} 项")
    return 0


def cmd_work(args) -> int:
    project = Path(args.project)
    if args.action == "new":
        if not args.title or not args.goal:
            raise ProjectError("work new 需要 --title 和 --goal")
        path = create_work_order(project, args.title, args.goal, status=args.status)
        print(f"已创建工单：{path}")
        return 0
    if args.action == "status":
        if not args.id or not args.status:
            raise ProjectError("work status 需要 --id 和 --status")
        path = set_work_order_status(project, args.id, args.status)
        print(f"已更新工单：{path}")
        return 0
    orders = load_work_orders(project)
    if args.json:
        print(json.dumps(orders, ensure_ascii=False, indent=2))
    elif not orders:
        print("当前工作区没有工单")
    else:
        for order in orders:
            print(f"{order['id']}  {order['status']:<8}  {order['title']}")
    return 0


def cmd_input(args) -> int:
    if args.action != "add":
        raise ProjectError(f"未知 input 操作：{args.action}")
    destination, item = add_provided_input(
        Path(args.project),
        args.file,
        role=args.role,
        authority=args.authority,
        verification=args.verification,
    )
    print(f"已登记用户材料：{item['id']}  {destination}")
    return 0


def cmd_program(args) -> int:
    if args.action == "init":
        if not args.id or not args.title:
            raise ProjectError("program init 需要 --id 和 --title")
        path = init_program(
            args.path,
            args.id,
            args.title,
            git=not args.no_git,
            allow_existing=args.allow_existing,
        )
        print(f"已创建 program：{path}")
        return 0
    if args.action == "attach":
        if not args.source:
            raise ProjectError("program attach 需要 source")
        path = attach_node(args.path, args.source, args.node_path)
        print(f"已挂载子节点：{path}")
        return 0
    if args.action == "status":
        status = program_status(args.path)
        print(json.dumps(status, ensure_ascii=False, indent=2) if args.json else
              f"{status['id']}  {status['distribution']}  {len(status['submodules'])} 个子模块")
        return 0
    if args.action == "check":
        errors, warnings = check_program(args.path, require_cloneable=args.require_cloneable)
        for message in errors:
            print(f"[ERROR] {message}")
        for message in warnings:
            print(f"[WARN ] {message}")
        print(f"program check：{len(errors)} error / {len(warnings)} warn")
        return 1 if errors else 0
    if args.action == "set-distribution":
        if not args.distribution:
            raise ProjectError("program set-distribution 需要 local 或 cloneable")
        meta = set_distribution(args.path, args.distribution)
        print(f"program distribution：{meta['distribution']}")
        return 0
    if args.action == "index":
        data = program_index(args.path)
        text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text, encoding="utf-8")
            print(f"已生成 program 索引：{output}")
        else:
            print(text, end="")
        return 0
    if args.action == "clone":
        if not args.source:
            raise ProjectError("program clone 需要 source 和 destination")
        destination = clone_program(args.path, args.source)
        print(f"已克隆 program：{destination}")
        return 0
    if args.action == "bundle":
        if not args.output:
            raise ProjectError("program bundle 需要 --output")
        output = bundle_program(args.path, args.output, force=args.force)
        print(f"已生成 program 迁移包：{output}")
        return 0
    raise ProjectError(f"未知 program 操作：{args.action}")


def cmd_ref(args) -> int:
    if args.action == "add":
        if not args.source_workspace or not args.artifact or not args.relation:
            raise ProjectError("ref add 需要 --source-workspace、--artifact 和 --relation")
        path, manifest = add_reference(
            Path(args.project),
            args.source_workspace,
            args.artifact,
            relation=args.relation,
            artifact_id=args.artifact_id,
        )
        print(f"已物化引用：{manifest['id']}  {path}")
        return 0
    errors = validate_references(Path(args.project))
    if args.action == "verify":
        if not args.search_root:
            raise ProjectError("ref verify 需要 --search-root")
        for status in verify_reference_authorities(Path(args.project), args.search_root):
            print(
                f"{status['id']}: {status['authority_state']} "
                f"target={status['target_workspace']} "
                f"pin={status['target_commit'] or '-'} "
                f"current={status['current_commit'] or '-'}"
            )
    for message in errors:
        print(f"[ERROR] {message}")
    print(f"引用检查：{len(errors)} error")
    return 1 if errors else 0


def cmd_synthesis(args) -> int:
    project = Path(args.project)
    if args.action == "init":
        print(init_synthesis(project))
        return 0
    if args.action == "validate":
        errors = validate_synthesis(project)
        for message in errors:
            print(f"[ERROR] {message}")
        print(f"synthesis：{len(errors)} error")
        return 1 if errors else 0
    if args.action == "build":
        outputs = build_synthesis_report(project, docx=args.docx)
        for kind, path in outputs.items():
            print(f"{kind}: {path}")
        return 0
    raise ProjectError(f"未知 synthesis 操作：{args.action}")


def cmd_cycle(args) -> int:
    from .cycle import init_cycle, capture, apply_records, cycle_status, read_json, validate
    project = Path(args.project)
    if args.action == "init":
        print(init_cycle(project))
    elif args.action == "capture":
        if not args.file or not args.id or not args.label:
            raise ProjectError("capture 需要 --file 项目内路径、--id、--label")
        print(capture(project, args.file, args.id, args.label))
    elif args.action == "apply":
        if not args.file:
            raise ProjectError("apply 需要 --file JSON 记录文件")
        print(f"已追加 {apply_records(project, read_json(args.file))} 条记录")
    elif args.action == "lint":
        errors = validate(project, read_json(project / "research/cycle.json"))
        for error in errors:
            print("[ERROR] " + error)
        print(f"研究循环：{len(errors)} error")
        return 1 if errors else 0
    else:
        print(json.dumps(cycle_status(project), ensure_ascii=False, indent=2))
    return 0


def cmd_research_ir(args) -> int:
    from .research_ir import (
        build_research_ir,
        snapshot_research_ir,
        validate_research_ir,
        write_research_ir,
    )

    project = Path(args.project)
    if args.action == "build":
        data = build_research_ir(project, revision=args.revision)
        out = write_research_ir(project, data, output=args.output or None)
        counts = data["assertions"]
        print(
            f"已生成 Research IR：{out}"
            f"（claims {len(counts['claims'])} / facts {len(counts['facts'])}"
            f" / conflicts {len(counts['conflicts'])}）"
        )
        return 0
    if args.action == "validate":
        source = Path(args.file) if args.file else project / "analysis/research-ir" / f"{args.revision}.json"
        if not source.is_absolute():
            source = project / source
        if not source.is_file():
            print(f"[ERROR] Research IR 不存在：{source}", file=sys.stderr)
            return 2
        data = json.loads(source.read_text(encoding="utf-8"))
        errors = validate_research_ir(project, data, verify_sources=args.check_sources)
        for error in errors:
            print(f"[ERROR] {error}")
        print(f"Research IR：{len(errors)} error")
        return 1 if errors else 0
    artifact_id = snapshot_research_ir(
        project,
        revision=args.revision,
        artifact_id=args.id,
        label=args.label,
    )
    print(f"已冻结 Research IR：{artifact_id}")
    return 0


def cmd_output(args) -> int:
    from .output_registry import (
        apply_records,
        init_registry,
        load_registry,
        output_status,
        validate_registry,
    )

    project = Path(args.project)
    if args.action == "init":
        print(init_registry(project))
    elif args.action == "apply":
        if not args.file:
            raise ProjectError("output apply 需要 --file JSON 记录文件")
        source = Path(args.file)
        if not source.is_absolute():
            source = project / source
        if not source.is_file():
            raise ProjectError(f"输出记录文件不存在：{source}")
        value = json.loads(source.read_text(encoding="utf-8"))
        print(f"已追加 {apply_records(project, value)} 条输出记录")
    elif args.action == "lint":
        data = load_registry(project)
        errors = validate_registry(project, data)
        for error in errors:
            print(f"[ERROR] {error}")
        print(f"输出登记：{len(errors)} error")
        return 1 if errors else 0
    else:
        print(json.dumps(output_status(project), ensure_ascii=False, indent=2))
    return 0


def cmd_deck(args) -> int:
    from .deck import build_pptx, convert_legacy_deck, validate_deck
    from .preview import render_powerpoint, validate_preview

    project = Path(args.project).resolve()

    def local(value: str) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = project / path
        path = path.resolve()
        if not path.is_relative_to(project):
            raise ProjectError("Deck 文件必须位于项目目录")
        return path

    if args.action == "convert":
        if not all((args.content, args.layout, args.snapshot, args.plan_id, args.plan_out, args.layout_out)):
            raise ProjectError("deck convert 需要 --content/--layout/--snapshot/--plan-id/--plan-out/--layout-out")
        plan, layout = convert_legacy_deck(
            project,
            local(args.content),
            local(args.layout),
            snapshot=args.snapshot,
            plan_id=args.plan_id,
            title=args.title,
        )
        plan_path = local(args.plan_out)
        layout_path = local(args.layout_out)
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        layout_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        layout_path.write_text(json.dumps(layout, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"已生成 DeckPlan：{plan_path}")
        print(f"已生成 RenderLayout：{layout_path}")
        return 0

    if args.action == "preview":
        if not args.pptx or not args.out_dir:
            raise ProjectError("deck preview 需要 --pptx 和 --out-dir")
        result = render_powerpoint(
            local(args.pptx),
            local(args.out_dir),
            width=args.width,
            height=args.height,
            contact_per_sheet=args.contact_per_sheet,
            contact_columns=args.contact_columns,
        )
        errors = validate_preview(local(args.out_dir), expected_slides=result["slides"])
        for error in errors:
            print(f"[ERROR] {error}")
        print(f"已生成 PowerPoint 预览：{local(args.out_dir)}（{result['slides']} 页，overflow {len(result['overflow'])}）")
        return 1 if errors else 0

    if not args.plan or not args.layout:
        raise ProjectError(f"deck {args.action} 需要 --plan 和 --layout")
    plan_path = local(args.plan)
    layout_path = local(args.layout)
    plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    layout = json.loads(layout_path.read_text(encoding="utf-8-sig"))
    if args.action == "validate":
        errors = validate_deck(plan, layout)
        for error in errors:
            print(f"[ERROR] {error}")
        print(f"Deck：{len(errors)} error")
        return 1 if errors else 0
    if not args.output:
        raise ProjectError("deck build 需要 --output")
    output = build_pptx(project, plan, layout, local(args.output))
    print(f"已生成原生 PPTX：{output}")
    return 0


def cmd_report_output(args, output_format: str) -> int:
    from .report_outputs import build_report, convert_legacy_report, inspect_report_output, validate_report_plan

    project = Path(args.project).resolve()

    def local(value: str) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = project / path
        path = path.resolve()
        if not path.is_relative_to(project):
            raise ProjectError("报告 Plan 与产物必须位于项目目录")
        return path

    if args.action == "convert":
        if not all((args.source, args.snapshot, args.plan_id, args.output)):
            raise ProjectError(
                f"{output_format} convert 需要 --source/--snapshot/--plan-id/--output"
            )
        plan = convert_legacy_report(
            project,
            local(args.source),
            snapshot=args.snapshot,
            plan_id=args.plan_id,
            output_format=output_format,
            title=args.title,
        )
        output = local(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"已生成 {plan['schema']}：{output}")
        return 0

    if not args.plan:
        raise ProjectError(f"{output_format} {args.action} 需要 --plan")
    plan_path = local(args.plan)
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ProjectError(f"无法读取报告 Plan：{plan_path}: {exc}") from exc
    if not isinstance(plan, dict):
        raise ProjectError("报告 Plan 必须是 JSON 对象")
    errors = validate_report_plan(plan, output_format)
    if args.action == "validate":
        for error in errors:
            print(f"[ERROR] {error}")
        print(f"{plan.get('schema', 'report plan')}：{len(errors)} error")
        return 1 if errors else 0
    if errors:
        raise ProjectError("\n".join(errors))
    if not args.output:
        raise ProjectError(f"{output_format} build 需要 --output")
    output = build_report(project, plan, local(args.output))
    inspection = inspect_report_output(output)
    print(f"已生成报告产物：{output}")
    print(json.dumps(inspection, ensure_ascii=False))
    if inspection.get("self_contained") is False:
        return 1
    return 0


def cmd_render(args) -> int:
    project = Path(args.project)
    if args.action == "build":
        try:
            document = build_document(project, Path(args.from_file) if args.from_file else None)
        except FileNotFoundError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 2
        out = write_document(project, document)
        sections = len(document.get("sections", []))
        print(f"已生成文档模型：{out}（{sections} 节）")
        return 0
    if args.action == "html":
        if args.from_file:
            document = build_document(project, Path(args.from_file))
            write_document(project, document)
        try:
            out = render_html(project)
        except FileNotFoundError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 2
        size = out.stat().st_size / 1024
        print(f"已生成自包含 HTML：{out}（{size:.0f} KB）")
        return 0
    if args.action == "docx":
        try:
            out = render_docx(project)
        except RenderDependencyError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 2
        except FileNotFoundError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 2
        size = out.stat().st_size / 1024
        print(f"已生成 Word：{out}（{size:.0f} KB）")
        return 0
    print(f"[ERROR] {args.action} 渲染尚未实现（P3）", file=sys.stderr)
    return 2


def _check(results: list, name: str, condition: bool, detail="") -> None:
    results.append((name, condition))
    mark = "PASS" if condition else "FAIL"
    suffix = "" if condition else f"  :: {detail}"
    print(f"[{mark}] {name}{suffix}")


def cmd_selftest(args) -> int:
    results: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        project = new_project("demo", "示例项目", root=root, git=False)
        clean = lint_project(project)
        _check(results, "脚手架产出通过 lint", clean.ok, clean.errors)
        _check(
            results,
            "非空目录不生成 .gitkeep",
            not (project / "_dev" / ".gitkeep").exists()
            and not (project / "search" / ".gitkeep").exists(),
        )
        _check(
            results,
            "空目录生成 .gitkeep",
            (project / "analysis" / "notes" / ".gitkeep").exists(),
        )
        _check(
            results,
            "呈现层工作区已生成",
            (project / "report" / "document.json").exists()
            and (project / "report" / "README.md").exists(),
        )
        release = project / "publish" / "v1.0"
        release.mkdir(parents=True)
        (release / "manifest.json").write_text(
            json.dumps({"version": "v1.0"}), encoding="utf-8"
        )
        (release / "README.md").write_text("packed output\n", encoding="utf-8")
        archive = pack_release(project, "v1.0")
        _check(
            results,
            "版本目录显式打包到 packed",
            archive == project / "publish" / "packed" / f"{project.name}-v1.0.zip"
            and archive.is_file(),
        )
        synthesis = new_project(
            "synthesis-demo",
            "示例总结",
            root=root,
            git=False,
            workflow="cycle",
            workspace_type="synthesis",
        )
        order = create_work_order(synthesis, "整理当前工作", "形成可追溯的工作汇总")
        synthesis_lint = lint_project(synthesis)
        _check(
            results,
            "总结型工作区与本地工单",
            (synthesis / "synthesis/ledger.json").is_file()
            and (synthesis / "work-model").is_dir()
            and order.is_file()
            and synthesis_lint.ok,
            synthesis_lint.errors,
        )
        demo_program = init_program(root / "program-demo", "prog-demo", "示例 Program")
        program_errors, _ = check_program(demo_program)
        _check(
            results,
            "Program 薄索引初始化",
            program_status(demo_program)["distribution"] == "local"
            and not program_errors,
            program_errors,
        )
        html_path = render_html(project)
        html_text = html_path.read_text(encoding="utf-8")
        _check(
            results,
            "HTML 渲染最小文档",
            html_path.exists() and "<html" in html_text and "决策支持材料" in html_text,
        )
        docx_ok = True
        if DOCX_AVAILABLE:
            docx_path = render_docx(project)
            docx_ok = docx_path.exists() and docx_path.stat().st_size > 1000
        _check(results, "DOCX 渲染最小文档", docx_ok)

        add_source(
            project,
            title="示例来源",
            tool="manual",
            locator="https://example.com/data",
            publisher="示例机构",
            grade="E1",
            query="示例",
            source_type="web",
        )
        with_source = lint_project(project)
        _check(results, "含来源项目通过 lint", with_source.ok, with_source.errors)

        batch = [
            {
                "title": "批量来源 A",
                "tool": "manual",
                "locator": "https://example.com/a",
                "publisher": "示例机构",
                "grade": "E2",
                "type": "web",
                "slug": "batch-a",
                "extracted": "# s-0002 · 批量来源 A\n\n关键摘录：A。\n",
            },
            {
                "title": "批量来源 B",
                "tool": "manual",
                "locator": "https://example.com/b",
                "publisher": "示例机构",
                "grade": "E3",
                "type": "web",
                "slug": "batch-b",
            },
        ]
        created = add_sources_batch(project, batch)
        batch_ok = len(created) == 2 and all(path.exists() for path in created)
        extracted_written = (
            (created[0] / "extracted.md").read_text(encoding="utf-8").startswith("# s-0002")
        )
        _check(results, "批量建来源成功", batch_ok)
        _check(results, "批量写入 extracted.md", extracted_written)
        _check(results, "批量来源项目通过 lint", lint_project(project).ok)

        meta_file = next((project / "search").glob("s-*/meta.json"))
        original = json.loads(meta_file.read_text(encoding="utf-8"))
        broken = dict(original)
        broken.pop("publisher")
        meta_file.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
        missing = lint_project(project)
        _check(results, "缺 meta 必填字段被检出", not missing.ok, missing.errors)
        meta_file.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")

        claims_file = project / "analysis" / "findings" / "claims.json"
        claims_file.write_text(
            json.dumps(
                {"claims": [{
                    "id": "c-0001",
                    "statement": "测试结论",
                    "confidence": "high",
                    "evidence": ["s-9999"],
                    "counter_evidence": [],
                    "scope": "测试",
                    "as_of": "2026-01-01",
                    "status": "active",
                }]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        dangling = lint_project(project)
        _check(results, "悬空证据引用被检出", not dangling.ok, dangling.errors)
        claims_file.write_text('{"claims": []}\n', encoding="utf-8")

        duplicate = project / "search" / "s-0002-duplicate"
        duplicate.mkdir()
        (duplicate / "meta.json").write_text(
            json.dumps({**original, "id": "s-0001"}, ensure_ascii=False),
            encoding="utf-8",
        )
        duplicated = lint_project(project)
        _check(results, "重复来源 id 被检出", not duplicated.ok, duplicated.errors)
        (duplicate / "meta.json").unlink()
        duplicate.rmdir()

        project_json = project / "project.json"
        project_meta = json.loads(project_json.read_text(encoding="utf-8"))
        project_meta["status"] = "analyzing"
        project_json.write_text(json.dumps(project_meta, ensure_ascii=False), encoding="utf-8")
        mismatched = lint_project(project)
        _check(results, "状态不一致被检出", not mismatched.ok, mismatched.errors)
        project_meta["status"] = "scoping"
        project_json.write_text(json.dumps(project_meta, ensure_ascii=False), encoding="utf-8")

        state_file = project / "_dev" / "03-调研状态.md"
        state_original = state_file.read_text(encoding="utf-8")
        state_file.write_text(
            state_original.replace("| G1 | ⚪ |", "| G1 | 🟡 |"), encoding="utf-8"
        )
        project_meta["gate_waivers"] = [{
            "gate": "G1",
            "reason": "测试豁免",
            "date": "2026-01-01",
            "approved_by": "manager",
        }]
        project_json.write_text(json.dumps(project_meta, ensure_ascii=False), encoding="utf-8")
        waived = lint_project(project)
        _check(results, "合法 waiver 通过", waived.ok, waived.errors)
        _check(
            results,
            "waiver 在 lint 中呈现",
            any("条件性通过" in info for info in waived.infos),
            waived.infos,
        )
        project_meta["gate_waivers"] = [{
            "gate": "G9",
            "reason": "非法门",
            "date": "2026-01-01",
            "approved_by": "manager",
        }]
        project_json.write_text(json.dumps(project_meta, ensure_ascii=False), encoding="utf-8")
        bad_waiver = lint_project(project)
        _check(results, "非法 gate waiver 被检出", not bad_waiver.ok, bad_waiver.errors)
        project_meta.pop("gate_waivers", None)
        project_json.write_text(json.dumps(project_meta, ensure_ascii=False), encoding="utf-8")
        state_file.write_text(state_original, encoding="utf-8")

        notes = project / "analysis" / "notes"
        for item in notes.iterdir():
            item.unlink()
        notes.rmdir()
        missing_dir = lint_project(project)
        _check(results, "缺目录被检出", not missing_dir.ok, missing_dir.errors)
        notes.mkdir()

        report_file = root / "report.md"
        report_file.write_text("结论[^s-9999]。\n", encoding="utf-8")
        bad_report = lint_project(project, report_path=report_file)
        _check(results, "报告悬空引用被检出", not bad_report.ok, bad_report.errors)

        claims_file.write_text(
            json.dumps(
                {"claims": [{
                    "id": "c-0001",
                    "statement": "已废弃结论",
                    "confidence": "high",
                    "evidence": ["s-0001"],
                    "counter_evidence": [],
                    "scope": "测试",
                    "as_of": "2026-01-01",
                    "status": "superseded",
                }]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        report_file.write_text("旧结论[^c-0001]，另见[^s-0002]。\n", encoding="utf-8")
        consistency = lint_project(project, report_path=report_file)
        _check(
            results,
            "报告引用非 active 结论被检出",
            not consistency.ok,
            consistency.errors,
        )
        _check(
            results,
            "报告引用未分析来源被警告",
            any("未被任何 claim/fact/conflict 使用" in item for item in consistency.warnings),
            consistency.warnings,
        )
        claims_file.write_text('{"claims": []}\n', encoding="utf-8")
        report_file.unlink()

        counts = status_counts(project)
        _check(results, "status 统计可读", counts["sources"] == 3 and counts["claims"] == 0)

    import unittest

    repo_root = Path(__file__).resolve().parents[2]
    tests_dir = repo_root / "tests"
    if tests_dir.is_dir():
        suite = unittest.defaultTestLoader.discover(str(tests_dir), pattern="test_cycle.py")
        test_result = unittest.TextTestRunner(verbosity=1).run(suite)
        _check(results, "专业调研循环行为回归", test_result.wasSuccessful() and test_result.testsRun > 0)
    elif (repo_root / "_dev").is_dir():
        _check(results, "专业调研循环行为回归", False, f"开发仓缺少测试目录：{tests_dir}")
    else:
        print("[INFO] 发布仓未携带开发测试；内置自检已运行，专业循环回归需在开发仓执行")
    failed = [name for name, ok in results if not ok]
    print(f"\nselftest：{len(results) - len(failed)}/{len(results)} 通过")
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sa",
        description="调研治理框架命令行（Study Arca）",
    )
    parser.add_argument("--version", action="version", version=f"sa {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new", help="新建工作区")
    new.add_argument("slug")
    new.add_argument("--title", default=None)
    new.add_argument("--root", default=None, help="工作区根目录，默认 <repo>/work-root（兼容 workspace）")
    new.add_argument("--date", default=None, help="YYYY-MM-DD，默认今天")
    new.add_argument("--type", dest="workspace_type", choices=sorted(WORKSPACE_TYPES), default="research")
    new.add_argument("--workflow", choices=["cycle", "legacy"], default="cycle")
    new.set_defaults(func=cmd_new)

    work = sub.add_parser("work", help="工作区本地工单")
    work.add_argument("action", choices=["new", "list", "status"])
    work.add_argument("project")
    work.add_argument("--id")
    work.add_argument("--title")
    work.add_argument("--goal")
    work.add_argument("--status", choices=sorted(WORK_ORDER_STATUS), default="proposed")
    work.add_argument("--json", action="store_true")
    work.set_defaults(func=cmd_work)

    input_parser = sub.add_parser("input", help="登记用户提供的材料")
    input_parser.add_argument("action", choices=["add"])
    input_parser.add_argument("project")
    input_parser.add_argument("--file", required=True)
    input_parser.add_argument("--role", choices=sorted(PROVIDED_ROLES), default="work_record")
    input_parser.add_argument("--authority", choices=sorted(PROVIDED_AUTHORITY), default="first_person")
    input_parser.add_argument(
        "--verification",
        choices=sorted(PROVIDED_VERIFICATION),
        default="self_reported",
    )
    input_parser.set_defaults(func=cmd_input)

    program = sub.add_parser("program", help="Program 薄索引与 Git 子模块")
    program.add_argument(
        "action",
        choices=[
            "init",
            "attach",
            "status",
            "check",
            "set-distribution",
            "index",
            "clone",
            "bundle",
        ],
    )
    program.add_argument("path")
    program.add_argument("source", nargs="?")
    program.add_argument("--id")
    program.add_argument("--title")
    program.add_argument("--path", dest="node_path")
    program.add_argument("--distribution", choices=["local", "cloneable"])
    program.add_argument("--require-cloneable", action="store_true")
    program.add_argument("--output")
    program.add_argument("--json", action="store_true")
    program.add_argument("--no-git", action="store_true")
    program.add_argument("--allow-existing", action="store_true")
    program.add_argument("--force", action="store_true")
    program.set_defaults(func=cmd_program)

    ref = sub.add_parser("ref", help="跨工作区引用与物化副本")
    ref.add_argument("action", choices=["add", "check", "verify"])
    ref.add_argument("project")
    ref.add_argument("--source-workspace")
    ref.add_argument("--artifact")
    ref.add_argument("--artifact-id")
    ref.add_argument("--relation", choices=sorted(REFERENCE_RELATIONS))
    ref.add_argument("--search-root")
    ref.set_defaults(func=cmd_ref)

    synthesis = sub.add_parser("synthesis", help="总结型工作区模型与报告")
    synthesis.add_argument("action", choices=["init", "validate", "build"])
    synthesis.add_argument("project")
    synthesis.add_argument("--docx", action="store_true")
    synthesis.set_defaults(func=cmd_synthesis)

    source = sub.add_parser("source", help="新建来源信封（单条或批量）")
    source.add_argument("project")
    source.add_argument("--batch", default=None, help="JSON 文件：来源数组或 {\"sources\": [...]}")
    source.add_argument("--title", default=None)
    source.add_argument("--tool", default=None)
    source.add_argument("--locator", default=None)
    source.add_argument("--publisher", default=None)
    source.add_argument("--grade", default="E1", choices=sorted(EVIDENCE_GRADES))
    source.add_argument("--type", default="web")
    source.add_argument("--query", default="")
    source.add_argument("--license", default="")
    source.add_argument("--notes", default="")
    source.add_argument("--slug", default=None, help="英文短 slug；中文标题建议显式给出")
    source.set_defaults(func=cmd_source)

    lint = sub.add_parser("lint", help="校验项目证据链")
    lint.add_argument("project")
    lint.add_argument("--report", default=None, help="同时校验报告引用")
    lint.add_argument("--stale-days", type=int, default=None)
    lint.add_argument("--strict", action="store_true", help="有警告也返回非零")
    lint.add_argument("--json", action="store_true")
    lint.set_defaults(func=cmd_lint)

    status = sub.add_parser("status", help="项目计数概览")
    status.add_argument("project")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    pack = sub.add_parser("pack", help="把指定发布版本显式打包到 publish/packed")
    pack.add_argument("project")
    pack.add_argument("--version", required=True, help="不可变版本目录名，例如 v1.0")
    pack.add_argument("--force", action="store_true", help="替换已存在的同名压缩包")
    pack.set_defaults(func=cmd_pack)

    dialect = sub.add_parser("dialect", help="本机用户方言")
    dialect.add_argument("action", choices=["init", "status", "import", "promote"])
    dialect.add_argument("--workspace")
    dialect.add_argument("--source")
    dialect.add_argument("--scope", choices=["user", "core"])
    dialect.add_argument("--output")
    dialect.set_defaults(func=cmd_dialect)

    render = sub.add_parser("render", help="呈现层：构建 document.json / 渲染 HTML")
    render.add_argument("action", choices=["build", "html", "docx", "pptx"])
    render.add_argument("project")
    render.add_argument("--from", dest="from_file", default=None, help="指定 Markdown 源文件")
    render.set_defaults(func=cmd_render)

    cycle = sub.add_parser("cycle", help="专业研究循环：约定、问题、讨论反馈与呈现记录")
    cycle.add_argument("action", choices=["init", "capture", "apply", "status", "lint"])
    cycle.add_argument("project")
    cycle.add_argument("--file")
    cycle.add_argument("--id")
    cycle.add_argument("--label")
    cycle.set_defaults(func=cmd_cycle)

    research_ir = sub.add_parser("research-ir", help="生成、校验或冻结 Research IR")
    research_ir.add_argument("action", choices=["build", "validate", "snapshot"])
    research_ir.add_argument("project")
    research_ir.add_argument("--revision", default="current")
    research_ir.add_argument("--file", default=None)
    research_ir.add_argument("--output", default=None)
    research_ir.add_argument("--id", default=None)
    research_ir.add_argument("--label", default=None)
    research_ir.add_argument(
        "--check-sources",
        action="store_true",
        help="同时校验当前来源和内容文件哈希",
    )
    research_ir.set_defaults(func=cmd_research_ir)

    output = sub.add_parser("output", help="独立输出登记：DOCX、HTML 和 PPT")
    output.add_argument("action", choices=["init", "apply", "status", "lint"])
    output.add_argument("project")
    output.add_argument("--file")
    output.set_defaults(func=cmd_output)

    deck = sub.add_parser("deck", help="DeckPlan/RenderLayout 转换、校验、原生 PPTX 编译与预览")
    deck.add_argument("action", choices=["convert", "validate", "build", "preview"])
    deck.add_argument("project")
    deck.add_argument("--content")
    deck.add_argument("--layout")
    deck.add_argument("--snapshot")
    deck.add_argument("--plan-id")
    deck.add_argument("--plan-out")
    deck.add_argument("--layout-out")
    deck.add_argument("--plan")
    deck.add_argument("--output")
    deck.add_argument("--title")
    deck.add_argument("--pptx")
    deck.add_argument("--out-dir")
    deck.add_argument("--width", type=int, default=2400)
    deck.add_argument("--height", type=int, default=1350)
    deck.add_argument("--contact-per-sheet", type=int, default=6)
    deck.add_argument("--contact-columns", type=int, default=2)
    deck.set_defaults(func=cmd_deck)

    for name, output_format in (("document", "docx"), ("experience", "html")):
        report = sub.add_parser(name, help=f"{output_format.upper()} 独立输出流程")
        report.add_argument("action", choices=["convert", "validate", "build"])
        report.add_argument("project")
        report.add_argument("--source")
        report.add_argument("--snapshot")
        report.add_argument("--plan-id")
        report.add_argument("--plan")
        report.add_argument("--output")
        report.add_argument("--title")
        report.set_defaults(func=lambda args, fmt=output_format: cmd_report_output(args, fmt))

    selftest = sub.add_parser("selftest", help="工具自身回归测试")
    selftest.set_defaults(func=cmd_selftest)

    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ProjectError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
