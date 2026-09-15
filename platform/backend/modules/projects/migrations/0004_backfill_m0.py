"""Add entry metadata for existing drafts without promoting preview/scientific state."""
import uuid
from django.db import migrations


def forward(apps, schema_editor):
    Scope = apps.get_model("projects", "ResearchConstraint")
    Edge = apps.get_model("projects", "DependencyEdge")
    Mutation = apps.get_model("projects", "MutationRecord")
    fields = ("object", "mechanism", "method", "outcome", "context", "years", "languages", "types", "include", "exclude", "resources")
    for scope in Scope.objects.all().iterator():
        Edge.objects.get_or_create(project_id=scope.project_id, source_id=scope.project_id,
            target_id=scope.pk, defaults={"target_kind": "scope"})
        if scope.status == "draft" and not scope.details:
            scope.details = {"answers": {key: "" for key in fields}, "candidates": [
                {"id": str(uuid.uuid4()), "term": term, "source": "project_keyword", "decision": "pending", "replacement": ""}
                for term in scope.core_keywords], "conflicts": [], "semantic_review": ""}
            scope.save(update_fields=("details",))
    for record in Mutation.objects.filter(actor=None).select_related("project").iterator():
        record.actor_id = record.project.owner_id
        record.save(update_fields=("actor",))


class Migration(migrations.Migration):
    dependencies = [("projects", "0003_dependencyedge_and_more")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
