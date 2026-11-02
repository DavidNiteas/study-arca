"""Public research-cycle interface: append-only records and frozen artifacts.

Contract: docs/09-专业调研循环.md. No engineering roles or gate semantics here.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
from contextlib import contextmanager
from datetime import datetime, date
from pathlib import Path

from .project import ProjectError

SCHEMA = 'sa.research/1'
DOMAINS = {'scoping', 'research', 'analysis', 'discussion', 'presentation'}
ID_RE = re.compile(r'^[a-z][a-z0-9-]{0,79}$')
REQUIRED = {
    'artifact': ('path', 'sha256', 'label'),
    'agreement': ('question', 'purpose', 'audience', 'scope', 'out_of_scope', 'as_of', 'acceptance', 'status'),
    'question': ('agreement', 'text'),
    'round': ('agreement', 'questions', 'trigger'),
    'discussion': ('round', 'questions', 'author', 'feedback', 'materials', 'disposition'),
    'action': ('round', 'question', 'discussion', 'domain', 'task', 'owner'),
    'outcome': ('action', 'status', 'summary', 'materials'),
    'answer': ('round', 'question', 'status', 'summary', 'materials', 'limitations'),
    'round_close': ('round', 'summary', 'unresolved'),
    'presentation': ('round', 'agreement', 'content', 'layout', 'output', 'preview', 'renderer', 'visual_review'),
}
TEXT_FIELDS = {'label', 'purpose', 'audience', 'scope', 'as_of', 'text', 'trigger', 'author',
               'feedback', 'task', 'owner', 'summary', 'renderer', 'status', 'disposition', 'domain'}
LIST_FIELDS = {'out_of_scope', 'acceptance', 'questions', 'materials', 'limitations', 'unresolved'}


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise ProjectError(f'无法读取 JSON {path}: {exc}') from exc


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def local_file(project, value):
    if not isinstance(value, str) or not value.strip():
        raise ProjectError('材料路径必须是非空字符串')
    root = Path(project).resolve()
    path = (root / value).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ProjectError(f'材料不存在或越出项目目录：{value}')
    return path


def validate(project, data):
    """Return human-readable errors; malformed input never masquerades as legacy."""
    errors = []
    if not isinstance(data, dict) or data.get('schema') != SCHEMA:
        return ['未知研究循环 schema；不会按旧项目静默解释']
    meta = read_json(Path(project) / 'project.json')
    if data.get('project') != meta.get('id'):
        errors.append('研究循环 project 与项目 ID 不一致')
    records = data.get('records')
    if not isinstance(records, list):
        return errors + ['records 必须是数组']
    seen = {}
    closed = set()
    outcomes = set()
    latest_approved = None
    answers = {}
    last_work = {}
    for number, record in enumerate(records):
        mark = f'records[{number}]'
        if not isinstance(record, dict):
            errors.append(mark + ' 必须是对象'); continue
        rid, kind = record.get('id'), record.get('type')
        if not isinstance(rid, str) or not ID_RE.fullmatch(rid) or rid in seen:
            errors.append(mark + ' id 非法或重复'); continue
        mark = rid
        if not isinstance(kind, str) or kind not in REQUIRED:
            errors.append(mark + ' 未知记录类型'); continue
        try:
            ts = datetime.fromisoformat(record.get('at', ''))
            if ts.tzinfo is None:
                raise ValueError()
        except (ValueError, TypeError):
            errors.append(mark + ' at 必须是带时区 ISO 时间')
        for field in REQUIRED[kind]:
            if field not in record:
                errors.append(f'{mark} 缺少 {field}')
            elif field in TEXT_FIELDS and (not isinstance(record[field], str) or not record[field].strip()):
                errors.append(f'{mark}.{field} 必须是非空文本')
            elif field in LIST_FIELDS and (not isinstance(record[field], list) or any(not isinstance(v, str) or not v.strip() for v in record[field])):
                errors.append(f'{mark}.{field} 必须是文本数组')
        for field in ('round', 'agreement', 'action', 'discussion', 'content', 'layout', 'output', 'preview', 'supersedes'):
            if field in record and (not isinstance(record[field], str) or not record[field].strip()):
                errors.append(f'{mark}.{field} 必须是非空引用 ID')
        if 'question' in record and (not isinstance(record['question'], str) or not record['question'].strip()):
            errors.append(mark + '.question 必须是非空文本或引用 ID')
        # Shape failures are handled before relationship checks to avoid unsafe coercion.
        if any(e.startswith(mark + ' ') or e.startswith(mark + '.') for e in errors):
            continue

        def ref(field, expected, value=None):
            value = record.get(field) if value is None else value
            target = seen.get(value) if isinstance(value, str) else None
            if not target or target['type'] != expected:
                errors.append(f'{mark}.{field} 必须引用前序 {expected}'); return {}
            return target

        def materials(field='materials'):
            values = record.get(field, [])
            if not isinstance(values, list) or not values:
                errors.append(f'{mark}.{field} 需要至少一个冻结材料'); return
            for value in values:
                ref(field, 'artifact', value)

        def round_ref():
            r = ref('round', 'round')
            if record.get('round') in closed and kind != 'presentation':
                errors.append(mark + ' 不能改写已关闭轮次；新建后续轮次')
            return r

        if kind == 'artifact':
            try:
                path = local_file(project, record['path'])
                if not path.is_relative_to((Path(project) / 'research/artifacts').resolve()):
                    errors.append(mark + ' 材料必须位于 research/artifacts')
                if not isinstance(record['sha256'], str) or digest(path) != record['sha256']:
                    errors.append(mark + ' 冻结材料哈希不一致')
            except ProjectError as exc:
                errors.append(f'{mark}: {exc}')
        elif kind == 'agreement':
            try:
                date.fromisoformat(record['as_of'])
            except ValueError:
                errors.append(mark + ' as_of 必须是 ISO 日期')
            if not isinstance(record['question'], str) or not record['question'].strip():
                errors.append(mark + ' question 必须是文本')
            if not record['acceptance']:
                errors.append(mark + ' acceptance 不可为空')
            if record['status'] not in ('draft', 'approved'):
                errors.append(mark + ' status 只能 draft/approved')
            if record.get('supersedes'):
                prior = ref('supersedes', 'agreement')
                if record['status'] == 'approved' and prior.get('status') == 'approved' and prior.get('id') != latest_approved:
                    errors.append(mark + ' 修订必须基于当前已批准约定')
                if not isinstance(record.get('change_reason'), str) or not record['change_reason'].strip():
                    errors.append(mark + ' 修订须有 change_reason')
            if record['status'] == 'approved':
                approval = record.get('approval')
                if not isinstance(approval, dict) or approval.get('actor') != 'user' or not isinstance(approval.get('statement'), str) or not approval['statement'].strip():
                    errors.append(mark + ' approved 需要用户批准原话及凭据')
                else:
                    ref('approval.artifact', 'artifact', approval.get('artifact'))
                if latest_approved and not record.get('supersedes'):
                    errors.append(mark + ' 新约定需显式 supersedes')
                latest_approved = rid
        elif kind == 'question':
            ref('agreement', 'agreement')
        elif kind == 'round':
            agreement = ref('agreement', 'agreement')
            if agreement.get('status') != 'approved' or agreement.get('id') != latest_approved:
                errors.append(mark + ' 新轮次必须绑定当前已批准约定')
            if not record['questions'] or len(set(record['questions'])) != len(record['questions']):
                errors.append(mark + ' questions 不可空或重复')
            for qid in record['questions']:
                q = ref('questions', 'question', qid)
                if q.get('agreement') != record['agreement']:
                    errors.append(mark + ' 问题与约定版本不一致')
        elif kind == 'discussion':
            r = round_ref(); materials()
            if not record['questions'] or any(q not in r.get('questions', []) for q in record['questions']):
                errors.append(mark + ' 讨论问题不属于本轮')
            if record['disposition'] not in ('follow_up', 'no_change'):
                errors.append(mark + ' disposition 只能 follow_up/no_change')
            if record['disposition'] == 'no_change' and not record.get('rationale'):
                errors.append(mark + ' 不采取动作须有 rationale')
            for q in record['questions']:
                last_work[(record['round'], q)] = number
        elif kind == 'action':
            r = round_ref(); q = ref('question', 'question'); discussion = ref('discussion', 'discussion')
            if record['domain'] not in DOMAINS:
                errors.append(mark + ' domain 非法')
            if q.get('id') not in r.get('questions', []) or record['question'] not in discussion.get('questions', []) or discussion.get('round') != record['round']:
                errors.append(mark + ' 任务、问题、讨论轮次不一致')
            last_work[(record['round'], record['question'])] = number
        elif kind == 'outcome':
            action = ref('action', 'action'); materials()
            if action.get('round') in closed:
                errors.append(mark + ' 已关闭轮次不可补写任务结果')
            if record['action'] in outcomes:
                errors.append(mark + ' 任务已有结果；返修须建新任务')
            if record['status'] not in ('done', 'deferred'):
                errors.append(mark + ' status 只能 done/deferred')
            if record['status'] == 'deferred' and not record.get('reason'):
                errors.append(mark + ' 延后任务须有 reason')
            outcomes.add(record['action'])
            last_work[(action.get('round'), action.get('question'))] = number
        elif kind == 'answer':
            r = round_ref(); ref('question', 'question'); materials()
            if record['question'] not in r.get('questions', []):
                errors.append(mark + ' 回答问题不属于本轮')
            if record['status'] not in ('answered', 'partial', 'insufficient'):
                errors.append(mark + ' 回答状态非法')
            if record['status'] != 'answered' and not record['limitations']:
                errors.append(mark + ' 部分回答/证据不足必须说明限制')
            answers[(record['round'], record['question'])] = number
        elif kind == 'round_close':
            r = round_ref()
            for q in r.get('questions', []):
                key = (record['round'], q)
                if answers.get(key, -1) <= last_work.get(key, -1):
                    errors.append(mark + ' 每个问题需在最新工作后形成回答')
            actions = [e for e in seen.values() if e['type'] == 'action' and e['round'] == record['round']]
            if any(e['id'] not in outcomes for e in actions):
                errors.append(mark + ' 仍有未登记结果的后续任务')
            discussions = [e for e in seen.values() if e['type'] == 'discussion' and e['round'] == record['round'] and e['disposition'] == 'follow_up']
            if any(not any(a['discussion'] == e['id'] for a in actions) for e in discussions):
                errors.append(mark + ' 有反馈尚未转为后续动作')
            partial = any(seen.get(records[answers[(record['round'], q)]]['id'], {}).get('status') != 'answered' for q in r.get('questions', []) if (record['round'], q) in answers)
            deferred = any(e['type'] == 'outcome' and e['status'] == 'deferred' and seen.get(e['action'], {}).get('round') == record['round'] for e in seen.values())
            if (partial or deferred) and not record['unresolved']:
                errors.append(mark + ' 未完全回答或延后任务需登记 unresolved')
            closed.add(record['round'])
        elif kind == 'presentation':
            r = round_ref(); ref('agreement', 'agreement')
            if record['agreement'] != r.get('agreement'):
                errors.append(mark + ' 呈现约定与轮次不一致')
            for field in ('content', 'layout', 'output', 'preview'):
                ref(field, 'artifact')
            v = record['visual_review']
            if not isinstance(v, dict) or v.get('status') not in ('pending', 'passed', 'failed'):
                errors.append(mark + ' visual_review 非法')
            elif v['status'] in ('passed', 'failed'):
                if v.get('viewed') is not True or not isinstance(v.get('reviewer'), str) or not v['reviewer'].strip() or not isinstance(v.get('notes'), str) or not v['notes'].strip() or v.get('mode') not in ('self', 'independent'):
                    errors.append(mark + ' 视觉审查需实际读图登记、人员、意见与复核身份')
        seen[rid] = record
    return errors


def ledger_path(project):
    return Path(project) / 'research/cycle.json'


def load_cycle(project):
    data = read_json(ledger_path(project))
    errors = validate(project, data)
    if errors:
        raise ProjectError('\n'.join(errors))
    return data


@contextmanager
def writer(project):
    directory = Path(project) / 'research'
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / '.cycle.lock'
    try:
        handle = lock.open('x', encoding='utf-8')
    except FileExistsError as exc:
        raise ProjectError('研究记录正被写入；若上次中断，核实无写者后再清理 .cycle.lock') from exc
    try:
        with handle:
            handle.write(str(os.getpid()))
        yield
    finally:
        lock.unlink()


def commit(project, data):
    errors = validate(project, data)
    if errors:
        raise ProjectError('\n'.join(errors))
    path = ledger_path(project)
    tmp = path.with_suffix('.tmp')
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def init_cycle(project):
    project = Path(project)
    meta = read_json(project / 'project.json')
    with writer(project):
        if ledger_path(project).exists():
            load_cycle(project)
            return ledger_path(project)
        commit(project, {'schema': SCHEMA, 'project': meta['id'], 'records': []})
        (project / 'research/README.md').write_text(
            '# 研究循环\n\n当前研究记录的唯一机器真相：cycle.json。使用 sa cycle status 查看问题、轮次和后续任务。\n'
            '记录由 sa cycle apply 追加；材料由 sa cycle capture 冻结。不要覆盖历史。\n'
            '业务协议见框架 docs/09-专业调研循环.md；代理入口见 docs/10-代理工作协议.md。\n', encoding='utf-8')
    return ledger_path(project)


def apply_records(project, records):
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list) or not records:
        raise ProjectError('输入必须是非空记录数组或单条记录')
    with writer(project):
        data = load_cycle(project)
        for value in records:
            record = copy.deepcopy(value)
            if not isinstance(record, dict):
                raise ProjectError('每条记录必须是对象')
            if record.get('type') == 'artifact':
                raise ProjectError('材料须由 cycle capture 登记')
            record.setdefault('at', datetime.now().astimezone().isoformat(timespec='seconds'))
            data['records'].append(record)
        commit(project, data)
    return len(records)


def capture(project, source, artifact_id, label):
    project = Path(project)
    if not ID_RE.fullmatch(artifact_id):
        raise ProjectError('材料 id 格式非法')
    source = local_file(project, source)
    with writer(project):
        data = load_cycle(project)
        if any(r['id'] == artifact_id for r in data['records']):
            raise ProjectError('材料 id 已使用')
        dest = project / 'research/artifacts' / artifact_id / source.name
        if dest.parent.exists():
            raise ProjectError('材料目录已存在；可能有未登记的中断产物，先检查')
        dest.parent.mkdir(parents=True)
        try:
            shutil.copyfile(source, dest)
            data['records'].append({'id': artifact_id, 'type': 'artifact', 'at': datetime.now().astimezone().isoformat(timespec='seconds'),
                                    'path': dest.relative_to(project).as_posix(), 'label': label, 'sha256': digest(dest)})
            commit(project, data)
        except Exception:
            dest.unlink(missing_ok=True)
            dest.parent.rmdir()
            raise
    return artifact_id


def cycle_status(project):
    data = load_cycle(project)
    records = data['records']
    closed = {r['round'] for r in records if r['type'] == 'round_close'}
    results = {r['action']: r for r in records if r['type'] == 'outcome'}
    answered = {(r['round'], r['question']): r for r in records if r['type'] == 'answer'}
    approved = [r for r in records if r['type'] == 'agreement' and r['status'] == 'approved']
    index = {r['id']: r for r in records}
    answer_positions = {(r['round'], r['question']): i for i, r in enumerate(records) if r['type'] == 'answer'}
    work_positions = {}
    for i, r in enumerate(records):
        if r['type'] == 'discussion':
            for q in r['questions']:
                work_positions[(r['round'], q)] = i
        elif r['type'] == 'action':
            work_positions[(r['round'], r['question'])] = i
        elif r['type'] == 'outcome':
            action = index[r['action']]
            work_positions[(action['round'], action['question'])] = i
    def answer_status(round_id, question_id):
        key = (round_id, question_id)
        if key not in answered:
            return 'unanswered'
        if answer_positions[key] < work_positions.get(key, -1):
            return 'needs_update'
        return answered[key]['status']
    return {'schema': SCHEMA, 'project': data['project'], 'current_agreement': approved[-1]['id'] if approved else None,
            'draft_agreements': [r['id'] for r in records if r['type'] == 'agreement' and r['status'] == 'draft'],
            'rounds': [{'id': r['id'], 'agreement': r['agreement'], 'status': 'closed' if r['id'] in closed else 'open',
                        'questions': [{'id': q, 'answer': answer_status(r['id'], q)} for q in r['questions']]}
                       for r in records if r['type'] == 'round'],
            'actions': [{'id': r['id'], 'domain': r['domain'], 'task': r['task'], 'status': results.get(r['id'], {}).get('status', 'open')} for r in records if r['type'] == 'action'],
            'presentations': [{'id': r['id'], 'round': r['round'], 'visual_review': r['visual_review']['status']} for r in records if r['type'] == 'presentation'],
            'records': len(records)}
