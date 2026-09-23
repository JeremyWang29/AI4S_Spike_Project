from modules.core import fingerprint
from .models import ConceptVersion


def formal_concepts_dto(project_id, scope_id):
    from config.errors import BusinessError
    from copy import deepcopy
    concept = ConceptVersion.objects.filter(project_id=project_id, scope_id=scope_id).first()
    if not concept:
        raise BusinessError("CONCEPT_VERSION_BLOCKED", "正式概念版本缺失", status=409, recovery="返回2A确认概念版本并刷新")
    return {"id": str(concept.id), "version": concept.version, "fingerprint": concept.fingerprint,
            "project_id": str(project_id), "scope_id": str(scope_id), "source": "accepted_concepts",
            "terms": deepcopy(concept.content.get("terms", [])),
            "decisions": deepcopy(concept.content.get("decisions", []))}


def freeze_concepts(project_id, scope):
    terms = []
    for candidate in scope.details.get("candidates", []):
        if candidate["decision"] in ("accepted", "replaced"):
            terms.append(candidate["replacement"] if candidate["decision"] == "replaced" else candidate["term"])
    content = {"terms": terms, "decisions": scope.details.get("candidates", []), "semantic_review": scope.details.get("semantic_review", "")}
    return ConceptVersion.objects.create(project_id=project_id, scope_id=scope.id, version=scope.version,
        content=content, fingerprint=fingerprint(content))
