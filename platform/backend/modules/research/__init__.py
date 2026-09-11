from dataclasses import dataclass
from modules.core import Blocker

GAP_TYPES = (
    "evidence_content", "object_population", "method", "theory_perspective",
    "context_geography_timeliness", "contradiction", "technology_practice_policy",
)

@dataclass(frozen=True)
class CandidateGate:
    gap_type: str
    primary_search_applicable: bool
    required_followups_complete: bool
    three_checks_complete: bool
    expert_reviewed: bool
    evidence_sufficient: bool
    def blockers(self):
        facts = {"primary_search": self.primary_search_applicable, "required_followups": self.required_followups_complete,
                 "three_checks": self.three_checks_complete, "expert_review": self.expert_reviewed,
                 "evidence": self.evidence_sufficient}
        return [Blocker("CANDIDATE_GATE_UNMET", f"候选门槛未满足: {k}", "reviewer", f"完成 {k}") for k, v in facts.items() if not v]
    @property
    def eligible(self): return self.gap_type in GAP_TYPES and not self.blockers()
