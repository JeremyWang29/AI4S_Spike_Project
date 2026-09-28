import uuid
from django.db import models


class ConceptVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_id = models.UUIDField(db_index=True)
    scope_id = models.UUIDField(unique=True)
    version = models.PositiveIntegerField()
    content = models.JSONField()
    fingerprint = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Confirmed concept content is immutable")
        return super().save(*args, **kwargs)


class GraphTerm(models.Model):
    """Imported, licensed terminology. A null project is a platform-wide record."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_id = models.UUIDField(null=True, blank=True, db_index=True)
    graph_version = models.CharField(max_length=120)
    concept_id = models.CharField(max_length=200)
    source_position = models.CharField(max_length=500)
    term = models.CharField(max_length=200)
    definition = models.TextField(blank=True)
    parent_keyword = models.CharField(max_length=200)
    relation = models.CharField(max_length=24)
    license = models.CharField(max_length=200)
    external_sharing_allowed = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('project_id', 'graph_version', 'concept_id', 'parent_keyword', 'relation'), name='graph_term_version_identity')]
