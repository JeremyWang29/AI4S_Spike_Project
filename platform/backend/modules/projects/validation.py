import math
from config.errors import BusinessError


def invalid(message="输入格式无效"):
    raise BusinessError("INVALID_INPUT", message, status=422)


def bounded_json(value, depth=0):
    if depth > 16: invalid("输入嵌套过深")
    if isinstance(value, dict):
        if len(value) > 100: invalid("字段过多")
        for key, child in value.items():
            if not isinstance(key, str) or len(key) > 160: invalid()
            bounded_json(child, depth + 1)
    elif isinstance(value, list):
        if len(value) > 200: invalid("列表过长")
        for child in value: bounded_json(child, depth + 1)
    elif isinstance(value, str):
        if len(value) > 10000: invalid("文本过长")
    elif isinstance(value, float) and not math.isfinite(value): invalid("数值必须有限")
    elif value is not None and not isinstance(value, (bool, int, float)): invalid()


def text(value, field, maximum=200, required=True):
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        invalid(field + " 必须是有效文本")
    return value.strip()


def count(value, field):
    if type(value) is not int or not 0 <= value <= 1_000_000_000:
        invalid(field + " 必须是有限非负整数")
    return value


def enumeration(value, allowed, field):
    if value not in allowed: invalid(field + " 选项无效")
    return value


def validate_ast(raw, depth=0):
    if depth > 8 or not isinstance(raw, dict): invalid("检索逻辑树无效或过深")
    kind = raw.get("type")
    if kind == "term":
        text(raw.get("field"), "field", 80)
        text(raw.get("value"), "value", 500)
    elif kind == "not": validate_ast(raw.get("child"), depth + 1)
    elif kind == "bool":
        enumeration(raw.get("op"), ("AND", "OR"), "op")
        children = raw.get("children")
        if not isinstance(children, list) or not 2 <= len(children) <= 20: invalid("逻辑节点数量无效")
        for child in children: validate_ast(child, depth + 1)
    else: invalid("检索节点类型无效")


def validate_legacy(action, data):
    for key in ("platform", "query_id", "run_id", "source_record_id", "snapshot_id", "search_report_id", "excerpt_hash", "file_hash", "candidate_id", "slice_version"):
        if key in data: text(data[key], key, 200)
    if action == "knowledge.evidence":
        enumeration(data.get("status"), ("supported", "insufficient", "conflicting", "not_retrieved"), "status")
    for key in ("filters",):
        if key in data and not isinstance(data[key], dict): invalid(key + " 必须为对象")
    if "executed_at" in data:
        from django.utils.dateparse import parse_datetime
        value = text(data["executed_at"], "executed_at", 80)
        try: parsed = parse_datetime(value)
        except ValueError: parsed = None
        if parsed is None or parsed.tzinfo is None: invalid("执行时间必须包含有效时区")
    if "scope" in data: enumeration(data["scope"], ("literature", "patent"), "scope")
    for key in ("total_hits", "parsed_count", "page"):
        if key in data: count(data[key], key)
    for key in ("complete_export", "human_verified", "roundtrip_equal", "confirmed", "license_valid"):
        if key in data and type(data[key]) is not bool: invalid(key + " 必须为布尔值")
    for key in ("evidence_ids", "approval_reviewers", "subset", "gap_types", "errors", "limitations"):
        if key in data and not isinstance(data[key], list): invalid(key + " 必须为列表")
    for key in ("evidence_ids", "approval_reviewers", "subset", "gap_types"):
        if any(not isinstance(value, str) or len(value) > 160 for value in data.get(key, [])): invalid(key + " 引用必须为文本")
    if action == "gold.evaluate":
        if not isinstance(data.get("checks", {}), dict): invalid("checks必须为对象")
        for stage in ("tuning", "acceptance"):
            group = data.get(stage)
            if not isinstance(group, dict): invalid("缺少评估分组")
            for key, value in group.items():
                if key in ("tp", "fp", "fn", "tn", "unknown_required"):
                    count(value, key)
    if action == "retrieval.compile":
        validate_ast(data.get("ast"))
        enumeration(data.get("kind", "formal_search"), ("coarse_search", "formal_search", "evidence_followup"), "kind")
