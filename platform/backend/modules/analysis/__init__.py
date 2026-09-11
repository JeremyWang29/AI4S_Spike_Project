from dataclasses import dataclass, replace
import uuid

@dataclass(frozen=True)
class SliceVersion:
    project_id: str
    definition: dict
    source_template_id: str | None = None
    id: str = ""
    def __post_init__(self):
        if not self.id: object.__setattr__(self, "id", str(uuid.uuid4()))

def apply_template(template, project_id):
    return SliceVersion(project_id, dict(template.definition), template.id)

def upgrade_slice(project_slice, template):
    return SliceVersion(project_slice.project_id, dict(template.definition), template.id)

def analytical_status(method_configured, raw_counts):
    return {"raw_counts": raw_counts, "labels": "READY" if method_configured else "UNCONFIGURED", "formal": bool(method_configured)}
