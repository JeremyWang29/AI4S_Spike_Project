from dataclasses import dataclass
from modules.core import fingerprint, Blocker


@dataclass(frozen=True)
class Term:
    field: str
    value: str


@dataclass(frozen=True)
class Bool:
    op: str
    children: tuple


@dataclass(frozen=True)
class Not:
    child: object


@dataclass(frozen=True)
class PlatformRule:
    platform: str
    version: int
    field_map: dict
    operators: tuple[str, ...]
    verified: bool
    license_verified: bool


def canonical(node):
    if isinstance(node, Term): return {"type": "term", "field": node.field, "value": node.value.strip()}
    if isinstance(node, Not): return {"type": "not", "child": canonical(node.child)}
    children = sorted((canonical(c) for c in node.children), key=lambda x: fingerprint(x))
    return {"type": "bool", "op": node.op.upper(), "children": children}


def compile_query(node, rule):
    if not rule.verified:
        return None, Blocker("PLATFORM_RULE_UNVERIFIED", "平台语法规则尚未核实", "platform_admin", "上传真实平台样例并完成反解析核对")
    if isinstance(node, Term):
        if node.field not in rule.field_map:
            return None, Blocker("FIELD_UNSUPPORTED", f"平台不支持字段 {node.field}", "researcher", "调整规范逻辑树")
        escaped = node.value.replace('"', '\\"')
        return f'{rule.field_map[node.field]}:"{escaped}"', None
    if isinstance(node, Not):
        child, blocker = compile_query(node.child, rule)
        return (None, blocker) if blocker else (f"NOT ({child})", None)
    if node.op.upper() not in rule.operators:
        return None, Blocker("OPERATOR_UNSUPPORTED", f"平台不支持 {node.op}", "platform_admin", "更新已核实规则")
    parts = []
    for child in node.children:
        text, blocker = compile_query(child, rule)
        if blocker: return None, blocker
        parts.append(f"({text})")
    return f" {node.op.upper()} ".join(parts), None


GATES = {
    "coarse_search": ("rule_verified", "license_verified", "ast_valid"),
    "formal_search": ("rule_verified", "license_verified", "ast_valid", "roundtrip_equal", "gold_qualified", "execution_recorded"),
    "evidence_followup": ("rule_verified", "license_verified", "ast_valid", "required_list_complete", "human_check_complete"),
}


def check_gates(kind, facts):
    missing = [name for name in GATES[kind] if not facts.get(name, False)]
    return [Blocker("GATE_UNMET", f"未满足检索关卡: {name}", "researcher", f"完成 {name} 并重试") for name in missing]
