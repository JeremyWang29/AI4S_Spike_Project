from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from modules.core import Blocker

FORMAL_CHECKS = (
    "platform_rule_valid",
    "syntax_capability_valid",
    "semantic_equivalence_valid",
    "not_exclusion_regression_passed",
    "actual_execution_verified",
)


class Hit(str, Enum):
    HIT = "hit"
    MISS = "miss"
    UNKNOWN = "unknown"


def combine(op, values):
    values = tuple(Hit(v) for v in values)
    if op.upper() == "OR":
        if Hit.HIT in values: return Hit.HIT
        return Hit.UNKNOWN if Hit.UNKNOWN in values else Hit.MISS
    if Hit.MISS in values: return Hit.MISS
    return Hit.UNKNOWN if Hit.UNKNOWN in values else Hit.HIT


@dataclass(frozen=True)
class GoldGroup:
    name: str
    tp: int
    fp: int
    fn: int
    tn: int
    unknown_required: int = 0

    @property
    def total(self): return self.tp + self.fp + self.fn + self.tn
    @property
    def has_both_labels(self): return self.tp + self.fn > 0 and self.fp + self.tn > 0
    @property
    def recall(self):
        d = self.tp + self.fn
        return None if d == 0 else Decimal(self.tp) / Decimal(d)
    @property
    def precision(self):
        d = self.tp + self.fp
        return None if d == 0 else Decimal(self.tp) / Decimal(d)


@dataclass(frozen=True)
class Evaluation:
    scope: str
    tuning: GoldGroup
    acceptance: GoldGroup
    checks: dict

    def blockers(self):
        out = []
        if self.tuning.total + self.acceptance.total < 50:
            out.append(Blocker("GOLD_TOO_SMALL", "有效 Gold 总量少于50", "researcher", "补充并复核 Gold"))
        for group in (self.tuning, self.acceptance):
            if not group.has_both_labels: out.append(Blocker("GOLD_LABEL_MISSING", f"{group.name}缺少正例或负例", "reviewer", "补齐正负例"))
            if group.recall is None or group.precision is None: out.append(Blocker("METRIC_DENOMINATOR_ZERO", f"{group.name}指标分母无效", "reviewer", "修正标注集"))
            elif group.recall < Decimal("0.85") or group.precision < Decimal("0.85"):
                out.append(Blocker("METRIC_BELOW_THRESHOLD", f"{group.name}未达到未舍入的0.85", "researcher", "调整检索式并重新执行"))
            if group.unknown_required: out.append(Blocker("REQUIRED_HIT_UNKNOWN", f"{group.name}有必要命中未核验", "researcher", "用原查询核验命中"))
        for name in FORMAL_CHECKS:
            if not self.checks.get(name, False):
                out.append(Blocker("CHECK_UNMET", f"未完成检查: {name}", "reviewer", f"完成 {name}"))
        return out

    @property
    def qualified(self): return not self.blockers()
