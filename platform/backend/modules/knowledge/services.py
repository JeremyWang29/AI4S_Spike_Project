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
            "decisions": deepcopy(concept.content.get("decisions", [])),
            "typed_terms": deepcopy(concept.content.get("typed_terms", []))}


def freeze_concepts(project_id, scope):
    terms = []
    for candidate in scope.details.get("candidates", []):
        if candidate["decision"] in ("accepted", "replaced") and candidate.get("relation", "original") == "original":
            terms.append(candidate["replacement"] if candidate["decision"] == "replaced" else candidate["term"])
    content = {"typed_terms": [dict(c, term=c.get("replacement") if c["decision"] == "replaced" else c["term"]) for c in scope.details.get("candidates", []) if c["decision"] in ("accepted", "replaced")], "terms": terms, "decisions": scope.details.get("candidates", []), "semantic_review": scope.details.get("semantic_review", "")}
    return ConceptVersion.objects.create(project_id=project_id, scope_id=scope.id, version=scope.version,
        content=content, fingerprint=fingerprint(content))
