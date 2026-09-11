from decimal import Decimal
import uuid

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated

from config.errors import BusinessError
from modules.assets import Contribution
from modules.core import fingerprint, require_revision
from modules.evaluation import Evaluation, GoldGroup
from modules.research import CandidateGate, GAP_TYPES
from modules.retrieval import Bool, Not, PlatformRule, Term, canonical, check_gates, compile_query
from modules.execution.models import Event, Outbox, Task
from .models import CreateRequest, MutationRecord, Project, ResearchConstraint, WorkflowProjection, WorkflowState


def _project(user, project_id, lock=False):
    query = Project.objects.select_for_update() if lock else Project.objects
    try:
        return query.get(pk=project_id, owner=user)
    except Project.DoesNotExist:
        raise BusinessError("PROJECT_NOT_FOUND", "项目不存在或无权访问", status=404,
                            recovery="检查项目成员资格")


def _state(project):
    return WorkflowState.objects.get_or_create(project=project, defaults={"data": {
        "queries": [], "runs": [], "imports": [], "evidence": [], "candidates": [],
        "decisions": [], "contributions": [], "rewards": [], "analysis": {"method": "UNCONFIGURED", "raw_counts": {}}
    }})[0]


def _normalize_keywords(values):
    if not isinstance(values, list):
        return []
    result = []
    seen = set()
    for value in values:
        term = str(value).strip()
        key = term.casefold()
        if term and key not in seen:
            result.append(term)
            seen.add(key)
    return result


def _project_payload(project):
    constraint = project.constraints.order_by("-version").first()
    projection = getattr(project, "projection", None)
    return {
        "id": str(project.id),
        "name": project.name,
        "revision": project.revision,
        "direction": constraint.direction if constraint else "",
        "core_keywords": constraint.core_keywords if constraint else [],
        "scope_version": constraint.version if constraint else None,
        "scope_status": constraint.status if constraint else "missing",
        "dependencies": project.required_dependencies,
        "workflow": {
            "current_step": projection.current_step if projection else "scope",
            "step_states": projection.step_states if projection else {},
            "blocking_items": projection.blocking_items if projection else [],
        },
    }


def _mutate(request, project_id, action, handler):
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        raise BusinessError("IDEMPOTENCY_KEY_REQUIRED", "缺少 Idempotency-Key", status=422,
                            recovery="为本次变更生成唯一幂等键")
    try: expected = int(request.data["expected_revision"])
    except (KeyError, TypeError, ValueError):
        raise BusinessError("EXPECTED_REVISION_REQUIRED", "缺少有效 expected_revision", status=422,
                            recovery="刷新项目后携带当前 revision")
    request_hash = fingerprint({"action": action, "body": request.data})
    with transaction.atomic():
        project = _project(request.user, project_id, lock=True)
        existing = MutationRecord.objects.filter(project=project, key=key).first()
        if existing:
            if existing.request_hash != request_hash:
                raise BusinessError("IDEMPOTENCY_CONFLICT", "同一幂等键对应不同请求", status=409,
                                    recovery="使用新幂等键重试")
            response = JsonResponse(existing.response)
            response["Idempotent-Replay"] = "true"
            return response
        require_revision(project.revision, expected)
        state = _state(project)
        result = handler(project, state, request.data)
        project.revision += 1
        project.save(update_fields=("revision", "updated_at"))
        state.save(update_fields=("data", "updated_at"))
        payload = {**result, "project_revision": project.revision}
        MutationRecord.objects.create(project=project, key=key, action=action, request_hash=request_hash, response=payload)
    return JsonResponse(payload)


def _parse_ast(raw):
    kind = raw.get("type")
    if kind == "term": return Term(raw["field"], raw["value"])
    if kind == "not": return Not(_parse_ast(raw["child"]))
    if kind == "bool": return Bool(raw["op"], tuple(_parse_ast(x) for x in raw["children"]))
    raise BusinessError("INVALID_QUERY_AST", "检索逻辑树无效", recovery="使用 term/bool/not 节点")


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return JsonResponse({"status": "ok", "acceptance": {"capacity": "UNVERIFIED", "rpo_rto": "UNVERIFIED",
                         "real_platforms": "UNCONFIGURED", "model_quality": "UNCONFIGURED"}})


@ensure_csrf_cookie
@csrf_protect
def session_login(request):
    if request.method != "POST":
        return JsonResponse({"authenticated": request.user.is_authenticated,
                             "username": request.user.get_username() if request.user.is_authenticated else None})
    user = authenticate(request, username=request.POST.get("username"), password=request.POST.get("password"))
    if user is None: raise BusinessError("LOGIN_FAILED", "账号或密码无效", status=403, recovery="检查邀请账号")
    login(request, user); return JsonResponse({"authenticated": True, "username": user.get_username()})


@csrf_protect
def session_logout(request):
    if request.method != "POST": raise BusinessError("METHOD_NOT_ALLOWED", "只允许 POST", status=405)
    logout(request); return JsonResponse({"authenticated": False})


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def projects_collection(request):
    if request.method == "GET":
        projects = Project.objects.filter(owner=request.user).order_by("-updated_at", "id")
        return JsonResponse({"items": [_project_payload(project) for project in projects]})

    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        raise BusinessError("IDEMPOTENCY_KEY_REQUIRED", "缺少 Idempotency-Key", status=422,
                            recovery="为本次建项生成唯一幂等键")
    try:
        expected_revision = int(request.data.get("expected_revision"))
    except (TypeError, ValueError):
        expected_revision = -1
    if expected_revision != 0:
        raise BusinessError("EXPECTED_REVISION_INVALID", "新建项目必须使用 expected_revision=0", status=422,
                            recovery="刷新项目列表后重新提交")

    name = str(request.data.get("name", "")).strip()
    direction = str(request.data.get("direction", "")).strip()
    keywords = _normalize_keywords(request.data.get("core_keywords", []))
    invalid = {}
    if not name: invalid["name"] = "请输入项目名称"
    if not direction: invalid["direction"] = "请输入研究方向"
    if not keywords: invalid["core_keywords"] = "至少输入一个有效关键词"
    if invalid:
        raise BusinessError("PROJECT_INPUT_INVALID", "项目信息不完整", status=422,
                            recovery="修正标记字段后重试", details={"fields": invalid})

    request_hash = fingerprint({"name": name, "direction": direction, "core_keywords": keywords,
                                "expected_revision": 0})
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        existing = CreateRequest.objects.filter(user=request.user, key=key).first()
        if existing:
            if existing.request_hash != request_hash:
                raise BusinessError("IDEMPOTENCY_CONFLICT", "同一幂等键对应不同请求", status=409,
                                    recovery="使用新幂等键重新提交")
            response = JsonResponse(existing.response, status=201)
            response["Idempotent-Replay"] = "true"
            return response

        project = Project.objects.create(
            name=name,
            owner=request.user,
            revision=1,
            required_dependencies={"literature": "not_started", "patent": "not_started"},
        )
        constraint = ResearchConstraint.objects.create(
            project=project, version=1, status="draft", direction=direction, core_keywords=keywords,
        )
        step_states = {"project": "complete", "scope": "current"}
        for step in ("platforms", "exploration", "seeds", "evaluation", "corpus", "analysis"):
            step_states[step] = "locked"
        WorkflowProjection.objects.create(
            project=project,
            current_step="scope",
            step_states=step_states,
            blocking_items=[{"code": "SCOPE_CONFIRMATION_REQUIRED", "message": "请完成范围访谈并确认",
                             "owner": "researcher", "recovery": "进入范围与概念步骤"}],
        )
        _state(project)
        event = Event.objects.create(
            stream_id=project.id,
            stream_seq=1,
            event_type="ProjectCreated",
            payload={"project_id": str(project.id), "constraint_id": str(constraint.id), "scope_version": 1},
        )
        Outbox.objects.create(event=event)
        payload = _project_payload(project)
        CreateRequest.objects.create(user=request.user, key=key, request_hash=request_hash, response=payload)
    return JsonResponse(payload, status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def project_status(request, project_id):
    project = _project(request.user, project_id)
    state = _state(project)
    return JsonResponse({**_project_payload(project), "domain_workflow": state.data, "gap_taxonomy": GAP_TYPES})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def evaluate_gold(request, project_id):
    def command(project, state, data):
        try:
            groups = {k: GoldGroup(k, **data[k]) for k in ("tuning", "acceptance")}
            result = Evaluation(data["scope"], groups["tuning"], groups["acceptance"], data.get("checks", {}))
        except (KeyError, TypeError, ValueError) as exc:
            raise BusinessError("INVALID_EVALUATION", "Gold评估输入不完整", details={"reason": str(exc)})
        item = {"id": str(uuid.uuid4()), "scope": result.scope, "qualified": result.qualified,
                "blockers": [b.__dict__ for b in result.blockers()]}
        state.data.setdefault("evaluations", []).append(item)
        project.required_dependencies = {**project.required_dependencies, result.scope: "qualified" if result.qualified else "blocked"}
        project.save(update_fields=("required_dependencies",))
        return item
    return _mutate(request, project_id, "gold.evaluate", command)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def compile_retrieval(request, project_id):
    def command(project, state, data):
        platform = data.get("platform", "")
        configured = getattr(settings, "AI4S_PLATFORM_RULES", {}).get(platform)
        if configured:
            rule = PlatformRule(platform, configured["version"], configured["field_map"], tuple(configured["operators"]),
                                configured.get("verified", False), configured.get("license_verified", False))
        else:
            rule = PlatformRule(platform, 0, {}, (), False, False)
        ast = _parse_ast(data.get("ast", {})); query, blocker = compile_query(ast, rule)
        facts = {"rule_verified": rule.verified, "license_verified": rule.license_verified,
                 "ast_valid": blocker is None, "roundtrip_equal": data.get("roundtrip_equal", False),
                 "gold_qualified": project.required_dependencies.get(data.get("scope", "literature")) == "qualified",
                 "execution_recorded": False}
        blockers = ([blocker] if blocker else []) + check_gates(data.get("kind", "formal_search"), facts)
        item = {"id": str(uuid.uuid4()), "platform": platform, "scope": data.get("scope", "literature"),
                "kind": data.get("kind", "formal_search"), "ast": canonical(ast), "compiled": query,
                "status": "blocked" if blockers else "ready", "blockers": [b.__dict__ for b in blockers]}
        state.data.setdefault("queries", []).append(item); return item
    return _mutate(request, project_id, "retrieval.compile", command)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def record_manual_run(request, project_id):
    def command(project, state, data):
        query = next((x for x in state.data.get("queries", []) if x["id"] == data.get("query_id")), None)
        if query is None: raise BusinessError("QUERY_NOT_FOUND", "检索式不存在", status=404)
        item = {"id": str(uuid.uuid4()), "query_id": query["id"], "platform": data.get("platform"),
                "executed_at": data.get("executed_at"), "total_hits": int(data.get("total_hits", 0)),
                "sort_order": data.get("sort_order"), "filters": data.get("filters", {}),
                "complete_export": bool(data.get("complete_export", False)), "status": "recorded"}
        state.data.setdefault("runs", []).append(item); return item
    return _mutate(request, project_id, "retrieval.manual_run", command)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def import_summary(request, project_id):
    def command(project, state, data):
        run = next((x for x in state.data.get("runs", []) if x["id"] == data.get("run_id")), None)
        if run is None: raise BusinessError("RUN_NOT_FOUND", "执行记录不存在", status=404)
        if not data.get("file_hash"): raise BusinessError("FILE_HASH_REQUIRED", "缺少原始文件指纹")
        parsed = int(data.get("parsed_count", 0)); errors = data.get("errors", [])
        item = {"id": str(uuid.uuid4()), "run_id": run["id"], "file_hash": data["file_hash"], "parsed_count": parsed,
                "errors": errors, "coverage": "complete" if run["complete_export"] and parsed >= run["total_hits"] else "partial",
                "status": "imported_with_errors" if errors else "imported"}
        state.data.setdefault("imports", []).append(item); return item
    return _mutate(request, project_id, "materials.import_summary", command)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_evidence(request, project_id):
    def command(project, state, data):
        status = data.get("status")
        allowed = {"supported", "insufficient", "conflicting", "not_retrieved"}
        if status not in allowed:
            raise BusinessError("INVALID_EVIDENCE_STATUS", "证据状态无效", details={"allowed": sorted(allowed)})
        if status == "not_retrieved":
            required = ("snapshot_id", "search_report_id")
            location = {"snapshot_id": data.get("snapshot_id"), "search_report_id": data.get("search_report_id")}
        else:
            required = ("source_record_id", "snapshot_id", "page", "excerpt_hash")
            location = {key: data.get(key) for key in required}
        missing = [key for key in required if location.get(key) in (None, "")]
        if missing:
            raise BusinessError("EVIDENCE_LOCATION_REQUIRED", "证据或检索覆盖结论必须可定位", details={"missing": missing})
        human_verified = bool(data.get("human_verified"))
        item = {"id": str(uuid.uuid4()), **location, "status": status, "human_verified": human_verified,
                "claim_status": "verified" if status == "supported" and human_verified else status}
        state.data.setdefault("evidence", []).append(item); return item
    return _mutate(request, project_id, "knowledge.evidence", command)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def navigation(request, project_id):
    project = _project(request.user, project_id); data = _state(project).data
    analysis = data.get("analysis", {"method": "UNCONFIGURED", "raw_counts": {}})
    blockers = []
    if not data.get("imports"): blockers.append({"code": "FIXED_CORPUS_REQUIRED", "message": "尚无固定语料", "owner": "researcher", "recovery": "完成导入并固定快照"})
    if analysis.get("method") != "ENABLED": blockers.append({"code": "ANALYSIS_METHOD_UNCONFIGURED", "message": "分析方法未配置", "owner": "method_reviewer", "recovery": "核实方法和真实样例"})
    return JsonResponse({"raw_counts": analysis.get("raw_counts", {}), "formal": not blockers, "blockers": blockers})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_candidate(request, project_id):
    def command(project, state, data):
        labels = tuple(data.get("gap_types", []))
        invalid = [x for x in labels if x not in GAP_TYPES]
        if not labels or invalid: raise BusinessError("INVALID_GAP_TAXONOMY", "空白类型不符合七类规则", details={"invalid": invalid, "allowed": GAP_TYPES})
        gate = CandidateGate(labels[0], bool(data.get("primary_search_applicable")), bool(data.get("required_followups_complete")),
                             bool(data.get("three_checks_complete")), bool(data.get("expert_reviewed")), bool(data.get("evidence_sufficient")))
        item = {"id": str(uuid.uuid4()), "question": data.get("question", ""), "gap_types": labels,
                "slice_version": data.get("slice_version"), "evidence_ids": data.get("evidence_ids", []),
                "status": "eligible" if gate.eligible else "discussion_draft", "blockers": [b.__dict__ for b in gate.blockers()]}
        state.data.setdefault("candidates", []).append(item); return item
    return _mutate(request, project_id, "research.candidate", command)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_decision(request, project_id):
    def command(project, state, data):
        candidate = next((x for x in state.data.get("candidates", []) if x["id"] == data.get("candidate_id")), None)
        if candidate is None: raise BusinessError("CANDIDATE_NOT_FOUND", "候选课题不存在", status=404)
        if candidate["status"] != "eligible": raise BusinessError("CANDIDATE_NOT_VALIDATED", "候选课题尚未通过补查与专家三关")
        item = {"id": str(uuid.uuid4()), "candidate_id": candidate["id"], "scope_version": data.get("scope_version"),
                "snapshot_id": data.get("snapshot_id"), "limitations": data.get("limitations", []), "status": "decision_ready"}
        state.data.setdefault("decisions", []).append(item); return item
    return _mutate(request, project_id, "research.decision", command)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def validate_contribution(request, project_id):
    def command(project, state, data):
        contribution = Contribution(str(request.user.id), tuple(data.get("subset", [])), data.get("description", ""))
        if data.get("confirmed"): contribution.confirm()
        for reviewer in set(data.get("approval_reviewers", [])): contribution.approve(reviewer)
        valid, reason = contribution.publishable(Decimal(str(data.get("current_overlap", 1))),
                                                  Decimal(str(data.get("submit_threshold", 0))), bool(data.get("license_valid")))
        kind = data.get("publication_type", "ordinary")
        eligibility_id = fingerprint({"project": str(project.id), "subset": sorted(contribution.subset), "description": contribution.description}) if valid and kind == "eligible_contribution" else None
        item = {"id": str(uuid.uuid4()), "valid": valid, "reason": reason, "publication_type": kind, "eligibility_id": eligibility_id}
        state.data.setdefault("contributions", []).append(item)
        reward_created = False
        if eligibility_id and eligibility_id not in {x["eligibility_id"] for x in state.data.get("rewards", [])}:
            state.data.setdefault("rewards", []).append({"eligibility_id": eligibility_id, "seconds": 7_776_000, "status": "queued"}); reward_created = True
        item["reward_created"] = reward_created; return item
    return _mutate(request, project_id, "assets.validate_contribution", command)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def model_status(request, project_id):
    project = _project(request.user, project_id)
    configured = getattr(settings, "AI4S_MODEL_QUALITY_BASELINE", None)
    return JsonResponse({"project_id": str(project.id), "status": "ENABLED" if configured else "UNCONFIGURED",
                         "external_processing": "DENIED" if not configured else "POLICY_CHECK_REQUIRED",
                         "recovery": "配置许可、项目策略、质量基线与预算" if not configured else None})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def task_status(request, project_id, task_id):
    _project(request.user, project_id)
    try: task = Task.objects.get(pk=task_id, project_id=project_id)
    except Task.DoesNotExist: raise BusinessError("TASK_NOT_FOUND", "任务不存在", status=404)
    return JsonResponse({"id": str(task.id), "kind": task.kind, "status": task.status,
                         "target_version_id": str(task.target_version_id), "fencing_token": task.fencing_token})
