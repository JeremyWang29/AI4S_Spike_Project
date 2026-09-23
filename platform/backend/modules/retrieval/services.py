from django.db import transaction
from config.errors import BusinessError
from modules.core import fingerprint
from modules.identity.authorization import require_project
from modules.identity.services import audit
from modules.projects.services import confirmed_scope_dto, register_plan_dependencies, plan_applicability, rebuild_projection
from modules.projects.validation import bounded_json, invalid, text
from modules.knowledge.services import formal_concepts_dto
from modules.execution.services import append_event
from .models import SearchPlan, SearchBlock, SearchPlanTask, SearchPlanBatch
from .decomposition import load_template, decompose, validate_structure


def mark_plan_needs_revalidation(project_id, plan_id):
    """Applicability is mutable metadata; fixed draft content remains untouched."""
    SearchPlan.objects.filter(project_id=project_id, pk=plan_id).update(applicability="needs_revalidation")


def plan_payload(plan):
    result = {field.name: getattr(plan, field.attname) for field in plan._meta.fields
              if field.name not in ("idempotency_key", "request_hash", "creation_response")}
    for key in ("id", "plan_id", "project_id", "scope_id", "concept_id"): result[key] = str(result[key])
    result["created_at"] = plan.created_at.isoformat()
    result["applicability"] = plan_applicability(plan.project_id, plan.id)
    for key, model in (("blocks", SearchBlock), ("tasks", SearchPlanTask), ("batches", SearchPlanBatch)):
        result[key] = [{**{f.name: getattr(child, f.attname) for f in model._meta.fields if f.name not in ("id", "plan")},
                        "plan_id": str(plan.plan_id), "version": plan.version} for child in model.objects.filter(plan=plan).order_by("pk")]
    return result


def read_plan(user, plan_id):
    plan = SearchPlan.objects.filter(pk=plan_id).first()
    if not plan: raise BusinessError("PLAN_NOT_FOUND", "方案不存在或无权访问", status=404)
    require_project(user, plan.project_id)
    return plan_payload(plan)


def list_plans(user, project_id):
    project = require_project(user, project_id)
    try:
        scope = confirmed_scope_dto(project)
        concept = formal_concepts_dto(project.id, scope["id"])
        inputs, blocker = {"scope_ref": {k: scope[k] for k in ("id", "version", "fingerprint")}, "concept_ref": {k: concept[k] for k in ("id", "version", "fingerprint")}}, None
    except BusinessError as exc:
        inputs, blocker = None, {"code": exc.code, "message": exc.message, "recovery": exc.recovery}
    return {"items": [plan_payload(plan) for plan in SearchPlan.objects.filter(project_id=project.id).order_by("-created_at")], "inputs": inputs, "blocker": blocker}


@transaction.atomic
def create_plan(user, project_id, data, key):
    # All authoritative reads, permission recheck, and writes share the project lock.
    project = require_project(user, project_id, "write", lock=True)
    if not isinstance(data, dict): invalid()
    bounded_json(data)
    if not key or len(key) > 160: raise BusinessError("IDEMPOTENCY_KEY_REQUIRED", "请提供有效幂等键", recovery="重新提交草稿")
    request_hash = fingerprint(data)
    existing = SearchPlan.objects.filter(project_id=project.id, created_by=user, idempotency_key=key).first()
    if existing:
        if existing.request_hash != request_hash: raise BusinessError("IDEMPOTENCY_CONFLICT", "同一幂等键对应不同输入", status=409, recovery="使用新幂等键重试")
        return existing.creation_response, True
    if set(data) - {"expected_revision", "scope_ref", "concept_ref", "research_title"}: invalid("草稿不接受确认、批准、激活或自定义结构字段")
    if type(data.get("expected_revision")) is not int or data["expected_revision"] != 0: invalid("新方案须使用 expected_revision=0")
    scope = confirmed_scope_dto(project)
    concept = formal_concepts_dto(project.id, scope["id"])
    for name, dto in (("scope_ref", scope), ("concept_ref", concept)):
        ref = data.get(name)
        if not isinstance(ref, dict) or ref != {k: dto[k] for k in ("id", "version", "fingerprint")}:
            raise BusinessError("INPUT_VERSION_CHANGED", "范围或概念版本已变化", status=409, recovery="刷新2A输入版本后重新生成草稿")
    title = data.get("research_title", project.name)
    text(title, "研究题目", 2000)
    snapshot = {"research_title": title, "title_source": "research_title_override" if "research_title" in data else "project.name", "project_name": project.name, "scope": scope, "concept": concept}
    template = load_template()
    content = decompose(snapshot, template)
    validate_structure(content, template)
    plan = SearchPlan.objects.create(project_id=project.id, created_by=user, idempotency_key=key, request_hash=request_hash,
        scope_id=scope["id"], scope_version=scope["version"], scope_fingerprint=scope["fingerprint"],
        concept_id=concept["id"], concept_version=concept["version"], concept_fingerprint=concept["fingerprint"],
        template_id=template["id"], template_version=template["version"], template_hash=fingerprint(template),
        input_snapshot=snapshot, content_fingerprint=fingerprint({"input": snapshot, "template": template, "content": content}), unresolved_items=content["unresolved_items"])
    for name, model in (("blocks", SearchBlock), ("tasks", SearchPlanTask), ("batches", SearchPlanBatch)):
        for item in content[name]: model.objects.create(plan=plan, **item)
    register_plan_dependencies(project, scope["id"], concept["id"], plan.id)
    append_event(project.id, "SearchPlanDraftCreated", {"plan_id": str(plan.id), "version": plan.version, "actor_id": user.pk})
    audit(user, "search_plan.draft_created", project.id)
    rebuild_projection(project)
    response = plan_payload(plan)
    # Receipt is initialized once in this transaction; draft content is never updated.
    SearchPlan.objects.filter(pk=plan.id).update(creation_response=response)
    return response, False
