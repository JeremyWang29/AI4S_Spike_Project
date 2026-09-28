from copy import deepcopy
import re
import uuid
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from config.errors import BusinessError
from modules.execution.models import Event, Inbox
from modules.knowledge.services import freeze_concepts
from .models import DependencyEdge, ResearchConstraint, WorkflowProjection
from .validation import text, enumeration, invalid
from . import guided

QUESTION_GROUPS = [
    {"id": "research", "title": "研究对象与机制", "fields": ["object", "mechanism", "method", "outcome", "context"]},
    {"id": "boundary", "title": "时间与文献边界", "fields": ["years", "languages", "types"]},
    {"id": "criteria", "title": "纳入与排除", "fields": ["include", "exclude"]},
    {"id": "resources", "title": "资源与可行性", "fields": ["resources"]},
]
ANSWER_FIELDS = [field for group in QUESTION_GROUPS for field in group["fields"]]


def initial_details(keywords=()):
    return {**guided.defaults(), "answers": {key: "" for key in ANSWER_FIELDS}, "candidates": [
        {"id": str(uuid.uuid4()), "term": term, "source": "project_keyword", "decision": "pending", "replacement": "", "relation": "original", "parent_keyword": term, "variant_selected": False}
        for term in keywords], "conflicts": [], "semantic_review": ""}


def scope_payload(scope):
    return {"id": str(scope.id), "version": scope.version, "status": scope.status, "direction": scope.direction,
            "core_keywords": scope.core_keywords, "details": scope.details,
            "confirmed_at": scope.confirmed_at.isoformat() if scope.confirmed_at else None}


def read_scope(project):
    versions = list(project.constraints.order_by("-version"))
    from .suggestions import config
    provider = config()
    from modules.knowledge.services import graph_terms_for, graph_candidate_is_current
    graph_available = bool(versions and graph_terms_for(project.id, versions[0].core_keywords))
    current = scope_payload(versions[0]) if versions else None
    if current and current['status'] == 'draft':
        current = deepcopy(current)
        graph_rows = graph_terms_for(project.id, current['core_keywords'])
        for candidate in current['details'].get('candidates', []):
            if candidate.get('source') == 'graph' and not graph_candidate_is_current(candidate, graph_rows):
                candidate['review_required'] = True
    return {"project_id": str(project.id), "external_processing_allowed": project.external_processing_allowed, "scope": current, "history": [scope_payload(item) for item in versions],
            "project_revision": project.revision, "groups": QUESTION_GROUPS,
            "providers": {"ai": "UNCONFIGURED" if not all(provider.get(k) for k in ('url','model','key')) else ('AVAILABLE' if project.external_processing_allowed else 'DENIED'), "knowledge_graph": "AVAILABLE" if graph_available else "NO_COVERAGE"}}


def confirmed_scope_dto(project):
    """Public selector; caller authorizes the project. No graph/full text is exposed."""
    from modules.core import fingerprint
    scope = project.constraints.order_by("-version").first()
    if not scope or scope.status != "confirmed":
        raise BusinessError("SCOPE_VERSION_BLOCKED", "请先确认当前范围", status=409, recovery="返回2A确认范围并刷新")
    content = {"direction": scope.direction, "core_keywords": scope.core_keywords,
               "answers": scope.details.get("answers", {}), "boundary": scope.details.get("boundary", {})}
    return {"id": str(scope.id), "version": scope.version, "fingerprint": fingerprint(content),
            "project_id": str(project.id), "source": "confirmed_scope", "content": deepcopy(content)}


def register_plan_dependencies(project, scope_id, concept_id, plan_id):
    for source in (scope_id, concept_id):
        DependencyEdge.objects.create(project=project, source_id=source, target_id=plan_id, target_kind="search_plan")


def plan_applicability(project_id, plan_id):
    return "needs_revalidation" if DependencyEdge.objects.filter(project_id=project_id, target_id=plan_id).exclude(applicability="current").exists() else "current"


def create_dependencies(project, scope):
    DependencyEdge.objects.create(project=project, source_id=project.id, target_id=scope.id, target_kind="scope")


def invalidate_dependents(project, source_id):
    pending, visited = [source_id], set()
    while pending:
        source = pending.pop()
        if source in visited: continue
        visited.add(source)
        edges = list(DependencyEdge.objects.filter(project=project, source_id=source))
        for edge in edges:
            if edge.applicability == "current":
                edge.applicability = "needs_revalidation"
                edge.save(update_fields=("applicability",))
                if edge.target_kind == "search_plan":
                    from modules.retrieval.services import mark_plan_needs_revalidation
                    mark_plan_needs_revalidation(project.id, edge.target_id)
            pending.append(edge.target_id)


def validate_details(details, confirming=False):
    if not isinstance(details, dict): invalid("范围详情必须为对象")
    answers = details.get("answers", {})
    if not isinstance(answers, dict) or set(answers) - set(ANSWER_FIELDS): invalid("访谈字段无效")
    for key in ANSWER_FIELDS:
        text(answers.get(key, ""), key, 2000, required=confirming and details.get("schema_version") != 2 and key not in ("include", "exclude"))
    years = answers.get("years", "").strip()
    if years and details.get('schema_version') != 2:
        match = re.fullmatch(r"(\d{4})\s*[-—–至]\s*(\d{4})", years)
        if not match or not 1800 <= int(match[1]) <= int(match[2]) <= timezone.now().year + 1:
            invalid("年份须为有效的起止年份，例如2020—2026")
    candidates, conflicts = details.get("candidates", []), details.get("conflicts", [])
    if not isinstance(candidates, list) or not isinstance(conflicts, list): invalid()
    ids, terms = set(), set()
    for item in candidates:
        if not isinstance(item, dict): invalid()
        ident = text(item.get("id"), "候选编号", 80)
        term = text(item.get("term"), "候选词", 200)
        if ident in ids: invalid("候选编号重复")
        ids.add(ident)
        enumeration(item.get("source"), ("manual", "project_keyword", "model", "graph"), "候选来源")
        enumeration(item.get("relation", "original"), guided.RELATIONS, "术语关系")
        text(item.get("parent_keyword", term), "父关键词", 200)
        if type(item.get("variant_selected", False)) is not bool: invalid("变体选择必须为布尔值")
        if type(item.get('review_required', False)) is not bool or type(item.get('conflict', False)) is not bool: invalid('复核状态无效')
        if item.get('source') == 'graph':
            for key, limit in (('concept_id',200),('source_position',500),('definition',4000),('graph_version',120),('license',200)):
                text(item.get(key), key, limit, required=key!='definition')
        if item.get('source') == 'model': text(item.get('source_position',''), '模型输出定位', 500, False)
        enumeration(item.get("decision"), ("pending", "accepted", "rejected", "replaced"), "候选决定")
        if item['source'] == 'project_keyword' and item['decision'] == 'replaced': invalid('原始关键词请在范围草稿中修改')
        if confirming and item.get('review_required') and item['decision'] in ('accepted','replaced'): invalid('候选词变化后请逐项复核')
        if confirming and item.get('conflict') and item['decision'] in ('accepted','replaced'):
            if not item.get('relation_reviewed'): invalid('冲突或歧义须人工核查关系')
            text(item.get('relation_review_reason',''), '关系核查理由', 2000)
        if item["decision"] == "replaced": term = text(item.get("replacement"), "替代词", 200)
        if item["decision"] in ("accepted", "replaced"):
            term_key=(item.get('parent_keyword',term).casefold(),term.casefold())
            if term_key in terms: invalid("同一原关键词下已接受候选词重复，请核查歧义或拒绝重复项")
            terms.add(term_key)
        if confirming and item["decision"] == "pending": invalid("请处理所有候选词")
    conflict_ids = set()
    for item in conflicts:
        if not isinstance(item, dict): invalid()
        ident = text(item.get("id"), "矛盾编号", 80)
        if ident in conflict_ids: invalid("矛盾编号重复")
        conflict_ids.add(ident)
        text(item.get("description"), "矛盾说明", 2000)
        text(item.get("resolution", ""), "解决记录", 2000, required=confirming)
    includes = {v.strip().casefold() for v in re.split(r"[,，;；\n]", answers.get("include", "")) if v.strip()}
    excludes = {v.strip().casefold() for v in re.split(r"[,，;；\n]", answers.get("exclude", "")) if v.strip()}
    if includes & excludes: invalid("纳入与排除条件有重复，请修改冲突条件并记录解决说明")
    text(details.get("semantic_review", ""), "人工语义核查说明", 4000, required=confirming)
    result = {"answers": {key: answers.get(key, "").strip() for key in ANSWER_FIELDS},
            "candidates": deepcopy(candidates), "conflicts": deepcopy(conflicts),
            "semantic_review": details.get("semantic_review", "").strip()}
    if details.get("schema_version") == 2:
        result.update({key: deepcopy(details[key]) for key in ("schema_version", "research_fields", "boundary", "legacy_boundary", "legacy_boundary_reviewed", "suggestion_receipt", "criteria_id") if key in details})
        result = guided.validate(result, confirming)
    return result


def scope_command(project, state, data):
    action = enumeration(data.get("action"), ("save", "confirm", "edit"), "action")
    scope = project.constraints.order_by("-version").first()
    if not scope: raise BusinessError("SCOPE_MISSING", "范围对象缺失，请先恢复项目")
    if action == "edit":
        if scope.status != "confirmed": raise BusinessError("SCOPE_NOT_CONFIRMED", "当前已是草稿", status=409)
        previous = scope
        scope = ResearchConstraint.objects.create(project=project, version=previous.version + 1, status="draft",
            direction=previous.direction, core_keywords=deepcopy(previous.core_keywords), details=guided.upgrade(previous.details))
        if scope.details.get('schema_version') == 2:
            for field in scope.details['research_fields'].values():
                if field.get('selected'):
                    field['review_required'] = True
            for candidate in scope.details.get('candidates', []):
                if candidate.get('source') in ('graph', 'model'):
                    candidate['review_required'] = True
            scope.save()
        create_dependencies(project, scope)
        invalidate_dependents(project, previous.id)
    else:
        if scope.status == "confirmed": raise BusinessError("SCOPE_IMMUTABLE", "已确认范围不可改写，请创建新草稿", status=409)
        proposed = validate_details(data.get("details", scope.details or initial_details(scope.core_keywords)), action == "confirm")
        if proposed.get('criteria_id') != scope.details.get('criteria_id'):
            invalid('纳排版本引用不能通过范围表单更改')
        next_keywords = data.get('core_keywords', scope.core_keywords)
        if not isinstance(next_keywords, list) or not next_keywords or any(not isinstance(k, str) or not k.strip() or len(k)>200 for k in next_keywords) or len(set(k.casefold() for k in next_keywords)) != len(next_keywords):
            invalid('项目关键词无效')
        if any(item.get('relation','original') != 'original' and item.get('parent_keyword') not in next_keywords and item['decision'] != 'rejected' for item in proposed['candidates']):
            invalid('扩展术语必须关联当前项目关键词')
        from .suggestions import verify_selections, reconcile
        verify_selections(project, scope, proposed)
        reconcile(proposed['candidates'])
        if action == 'confirm' and any(c.get('conflict') and c['decision'] in ('accepted','replaced') and
                (not c.get('relation_reviewed') or not str(c.get('relation_review_reason','')).strip())
                for c in proposed['candidates']):
            invalid('同形异义或关系冲突须先保存并逐项核查')
        from modules.knowledge.services import graph_terms_for, graph_candidate_is_current
        graph_rows = graph_terms_for(project.id, next_keywords)
        for candidate in proposed['candidates']:
            if candidate.get('source') == 'graph' and not graph_candidate_is_current(candidate, graph_rows):
                candidate['review_required'] = True
                if action == 'confirm' and candidate['decision'] in ('accepted','replaced'):
                    invalid('图谱版本或权限变化后请复核候选词')
        next_direction = text(data.get('direction',scope.direction), "研究方向", 2000)
        changed_fields = next_direction != scope.direction or next_keywords != scope.core_keywords or any(
            proposed.get('research_fields',{}).get(key,{}).get(part) != scope.details.get('research_fields',{}).get(key,{}).get(part)
            for key in guided.FIELDS for part in ('status','text'))
        if changed_fields:
            for field in proposed.get('research_fields',{}).values():
                if field.get('selected'): field['review_required'] = True
            for candidate in proposed['candidates']:
                if candidate.get('source') in ('model','graph'):
                    candidate['review_required'] = True
            if action == 'confirm' and (any(field.get('review_required') for field in proposed.get('research_fields',{}).values()) or any(c.get('review_required') for c in proposed['candidates'])):
                invalid('范围变化后请先保存并逐项复核建议')
        if action == 'confirm' and next_keywords != scope.core_keywords:
            invalid('请先保存关键词修改，再确认范围')
        if action == 'confirm' and any(c['source']=='project_keyword' and c['term'] not in next_keywords and c['decision']!='rejected' for c in proposed['candidates']):
            invalid('已移除原关键词须明确拒绝')
        if action == 'confirm' and any(not any(
            c['source'] == 'project_keyword' and c['term'] == keyword and c['decision'] == 'accepted'
            for c in proposed['candidates']) for keyword in next_keywords):
            invalid('当前项目关键词须逐条接受；如需删除请先修改范围草稿')
        added_keyword_ids = set()
        if next_keywords != scope.core_keywords:
            existing = {c['term'].casefold() for c in proposed['candidates'] if c['source'] == 'project_keyword'}
            for keyword in next_keywords:
                if keyword.casefold() not in existing:
                    ident = str(uuid.uuid4())
                    added_keyword_ids.add(ident)
                    proposed['candidates'].append({'id':ident,'term':keyword,
                        'source':'project_keyword','decision':'pending','replacement':'',
                        'relation':'original','parent_keyword':keyword,'variant_selected':False})
            for candidate in proposed['candidates']:
                if candidate['source']=='project_keyword' and candidate['term'] not in next_keywords:
                    candidate['review_required']=True
        for collection, fixed_fields in (("candidates", ("term", "source", "relation", "parent_keyword", "reason", "concept_id", "source_position", "definition", "graph_version", "license", "external_sharing_allowed")), ("conflicts", ("description",))):
            incoming = {item["id"]: item for item in proposed[collection]}
            for previous in scope.details.get(collection, []):
                current = incoming.get(previous["id"])
                if not current or any(current.get(field) != previous.get(field) for field in fixed_fields):
                    invalid("已有候选来源或矛盾记录不可删除、改写；请记录决定或解决说明")
            previous_ids = {item["id"] for item in scope.details.get(collection, [])}
            if collection == "candidates" and any(item["id"] not in previous_ids and item["id"] not in added_keyword_ids and item["source"] not in ("manual", "model", "graph") for item in proposed[collection]):
                invalid("新候选只能声明为人工输入")
            if collection == "candidates" and any(item["id"] not in previous_ids and item["source"] == "manual" and item.get("relation") == "original" for item in proposed[collection]):
                invalid("原始关键词请在范围草稿中修改；人工候选请选择派生词关系")
        scope.details = proposed
        if "direction" in data: scope.direction = next_direction
        if next_keywords != scope.core_keywords: scope.core_keywords = next_keywords
        if action == "confirm":
            scope.status, scope.confirmed_at = "confirmed", timezone.now()
        scope.save()
        if action == "confirm":
            concept = freeze_concepts(project.id, scope)
            DependencyEdge.objects.create(project=project, source_id=scope.id, target_id=concept.id, target_kind="concept")
    return read_scope(project)


@transaction.atomic
def rebuild_projection(project):
    # Project lock serializes event append and the consistent reconstruction watermark.
    type(project).objects.select_for_update().get(pk=project.pk)
    scope = project.constraints.order_by("-version").first()
    confirmed = bool(scope and scope.status == "confirmed")
    steps = {"project": "complete", "scope": "complete" if confirmed else "current"}
    steps.update({step: "locked" for step in ("platforms", "exploration", "seeds", "evaluation", "corpus", "analysis")})
    blockers = [] if confirmed else [{"code": "SCOPE_CONFIRMATION_REQUIRED", "message": "请完成范围访谈并确认", "recovery": "进入范围与概念步骤"}]
    if confirmed: blockers = [{"code": "M1_UNCONFIGURED", "message": "范围已保存；正式检索准备尚未启用", "recovery": "等待M1验收"}]
    watermark = Event.objects.filter(stream_id=project.id).aggregate(value=Max("stream_seq"))["value"] or 0
    projection, _ = WorkflowProjection.objects.update_or_create(project=project, defaults={"current_step": "scope",
        "step_states": steps, "blocking_items": blockers, "source_stream_watermarks": {str(project.id): watermark}})
    for event_id in Event.objects.filter(stream_id=project.id, stream_seq__lte=watermark).values_list("id", flat=True):
        Inbox.objects.get_or_create(consumer="workflow_projection", event_id=event_id)
    return projection
