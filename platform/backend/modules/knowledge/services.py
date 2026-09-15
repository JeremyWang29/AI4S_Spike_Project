from modules.core import fingerprint
from .models import ConceptVersion


def freeze_concepts(project_id, scope):
    terms = []
    for candidate in scope.details.get("candidates", []):
        if candidate["decision"] in ("accepted", "replaced"):
            terms.append(candidate["replacement"] if candidate["decision"] == "replaced" else candidate["term"])
    content = {"terms": terms, "decisions": scope.details.get("candidates", []), "semantic_review": scope.details.get("semantic_review", "")}
    return ConceptVersion.objects.create(project_id=project_id, scope_id=scope.id, version=scope.version,
        content=content, fingerprint=fingerprint(content))
