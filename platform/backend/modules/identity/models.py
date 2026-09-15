import uuid
from django.conf import settings
from django.db import models


class CredentialToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    kind = models.CharField(max_length=12)
    digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True)


class LoginAttempt(models.Model):
    key = models.CharField(primary_key=True, max_length=64)
    failures = models.PositiveIntegerField(default=0)
    window_start = models.DateTimeField()


class AuditRecord(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=120)
    object_id = models.CharField(max_length=160)
    occurred_at = models.DateTimeField(auto_now_add=True)


class ProjectMembership(models.Model):
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=16, choices=[("researcher", "researcher"), ("reviewer", "reviewer")])
    assigned_actions = models.JSONField(default=list)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("project", "user"), name="project_member_once")]
