import uuid
from django.conf import settings
from django.db import models


class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    revision = models.PositiveIntegerField(default=1)
    required_dependencies = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "projects"


class ResearchConstraint(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="constraints")
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=24, default="draft")
    direction = models.TextField()
    core_keywords = models.JSONField(default=list)
    details = models.JSONField(default=dict)
    confirmed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self._state.adding and type(self).objects.filter(pk=self.pk, status="confirmed").exists():
            raise ValueError("Confirmed research constraint is immutable")
        return super().save(*args, **kwargs)

    class Meta:
        app_label = "projects"
        constraints = [models.UniqueConstraint(fields=("project", "version"), name="project_constraint_version")]


class WorkflowProjection(models.Model):
    project = models.OneToOneField(Project, primary_key=True, on_delete=models.CASCADE, related_name="projection")
    current_step = models.CharField(max_length=40, default="scope")
    step_states = models.JSONField(default=dict)
    blocking_items = models.JSONField(default=list)
    source_stream_watermarks = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "projects"


class CreateRequest(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    key = models.CharField(max_length=160)
    request_hash = models.CharField(max_length=64)
    response = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "projects"
        constraints = [models.UniqueConstraint(fields=("user", "key"), name="user_project_create_key")]


class WorkflowState(models.Model):
    project = models.OneToOneField(Project, primary_key=True, on_delete=models.CASCADE, related_name="workflow")
    data = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "projects"


class MutationRecord(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    key = models.CharField(max_length=160)
    action = models.CharField(max_length=120)
    request_hash = models.CharField(max_length=64)
    response = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "projects"
        constraints = [models.UniqueConstraint(fields=("project", "actor", "key"), name="project_actor_idempotency_key")]


class DependencyEdge(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="dependency_edges")
    source_id = models.UUIDField(db_index=True)
    target_id = models.UUIDField(db_index=True)
    target_kind = models.CharField(max_length=80)
    applicability = models.CharField(max_length=32, default="current")
    approval_content = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("project", "source_id", "target_id"), name="dependency_edge_once")]
