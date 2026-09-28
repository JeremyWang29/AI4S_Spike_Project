from modules.core import fingerprint
from django.db.models import Q
from .models import ConceptVersion, GraphTerm


def import_graph_terms(project_id, graph_version, license_name, rows, *, external_sharing_allowed=False,
                       platform_wide_authorized=False):
    """Import a validated graph release; callers must authorize the project/import source."""
    from collections import Counter
    from django.db import transaction
    from modules.projects.guided import RELATIONS
    from modules.projects.validation import invalid, text
    if project_id is None and not platform_wide_authorized:
        invalid('平台范围图谱必须经管理员确认许可覆盖全部试点项目；其他图谱须限定项目')
    if not isinstance(rows, list) or len(rows) > 10000: invalid('图谱导入格式无效')
    version = text(graph_version, '图谱版本', 120)
    license_name = text(license_name, '图谱许可', 200)
    normalized = []
    for row in rows:
        if not isinstance(row, dict): invalid('图谱术语格式无效')
        relation = row.get('relation')
        if relation not in RELATIONS[1:]: invalid('图谱术语关系无效')
        concept_id=text(row.get('concept_id'), '概念标识', 200)
        normalized.append(GraphTerm(project_id=project_id, graph_version=version,
            concept_id=concept_id,
            source_position=text(row.get('source_position'), '来源定位', 500),
            term=text(row.get('term'), '图谱术语', 200),
            definition=text(row.get('definition', ''), '定义', 4000, False),
            parent_keyword=text(row.get('parent_keyword'), '原关键词', 200),
            relation=relation, license=license_name,
            external_sharing_allowed=external_sharing_allowed))
    if any(count > 100 for count in Counter(row.parent_keyword for row in normalized).values()):
        invalid('同一原关键词的图谱候选不得超过100项；请先由管理员筛选导入')
    fields = ('concept_id', 'source_position', 'term', 'definition', 'parent_keyword',
              'relation', 'license', 'external_sharing_allowed', 'active')
    with transaction.atomic():
        GraphTerm.objects.select_for_update().filter(project_id=project_id, active=True).exclude(
            graph_version=version).update(active=False)
        existing = GraphTerm.objects.select_for_update().filter(project_id=project_id, graph_version=version)
        old_rows = sorted(tuple(getattr(row, field) for field in fields) for row in existing)
        new_rows = sorted(tuple(getattr(row, field) for field in fields) for row in normalized)
        if old_rows == new_rows:
            return len(normalized)
        existing.delete()
        GraphTerm.objects.bulk_create(normalized)
    return len(normalized)


def graph_terms_for(project_id, keywords):
    """Read only records licensed to this project or the platform."""
    rows = GraphTerm.objects.filter(Q(project_id=project_id) | Q(project_id__isnull=True),
        active=True, parent_keyword__in=keywords).order_by('parent_keyword', 'term', 'concept_id', 'id')
    return [{'id': str(row.id), 'concept_id': row.concept_id, 'source_position': row.source_position, 'term': row.term,
             'definition': row.definition, 'parent_keyword': row.parent_keyword,
             'relation': row.relation, 'graph_version': row.graph_version,
             'license': row.license, 'external_sharing_allowed': row.external_sharing_allowed,
             'source': 'graph'} for row in rows]


def graph_candidate_is_current(candidate, rows):
    for row in rows:
        if row['id'] == candidate.get('id'):
            return all(candidate.get(key) == row[key] for key in
                       ('concept_id','source_position','term','definition','parent_keyword','relation','graph_version','license','external_sharing_allowed'))
    return False


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
        if candidate["decision"] in ("accepted", "replaced") and candidate.get("relation", "original") == "original" and not candidate.get('review_required') and (not candidate.get('conflict') or (candidate.get('relation_reviewed') and candidate.get('relation_review_reason'))):
            terms.append(candidate["replacement"] if candidate["decision"] == "replaced" else candidate["term"])
    content = {"typed_terms": [dict(c, term=c.get("replacement") if c["decision"] == "replaced" else c["term"]) for c in scope.details.get("candidates", []) if c["decision"] in ("accepted", "replaced") and not c.get('review_required') and (not c.get('conflict') or (c.get('relation_reviewed') and c.get('relation_review_reason')))], "terms": terms, "decisions": scope.details.get("candidates", []), "semantic_review": scope.details.get("semantic_review", "")}
    return ConceptVersion.objects.create(project_id=project_id, scope_id=scope.id, version=scope.version,
        content=content, fingerprint=fingerprint(content))
