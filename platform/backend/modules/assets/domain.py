from dataclasses import dataclass, field
from modules.core import fingerprint
from config.errors import BusinessError

@dataclass
class Contribution:
    contributor_id: str
    subset: tuple[str, ...]
    description: str
    consent_fingerprint: str | None = None
    reviewer_approvals: set = field(default_factory=set)
    def confirm(self): self.consent_fingerprint = fingerprint({"subset": sorted(self.subset), "description": self.description})
    def modify(self, subset, description=None):
        self.subset = tuple(subset); self.description = self.description if description is None else description
        self.consent_fingerprint = None; self.reviewer_approvals.clear()
    def approve(self, reviewer): self.reviewer_approvals.add(reviewer)
    def publishable(self, current_overlap, submit_threshold, license_valid):
        current = fingerprint({"subset": sorted(self.subset), "description": self.description})
        if self.consent_fingerprint != current: return False, "CONSENT_STALE"
        if len(self.reviewer_approvals) < 2: return False, "DUAL_REVIEW_REQUIRED"
        if not license_valid: return False, "LICENSE_INVALID"
        if current_overlap > submit_threshold: return False, "OVERLAP_TOO_HIGH"
        return True, None
