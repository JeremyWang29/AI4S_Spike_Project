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
