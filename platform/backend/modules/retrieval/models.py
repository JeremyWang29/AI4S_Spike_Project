import uuid
from django.conf import settings
from django.db import models


class Immutable(models.Model):
    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Search plan draft content is immutable")
        return super().save(*args, **kwargs)

    class Meta:
        abstract = True


class SearchPlan(Immutable):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan_id = models.UUIDField(default=uuid.uuid4)
    project_id = models.UUIDField(db_index=True)
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=24, default="draft")
    applicability = models.CharField(max_length=32, default="current")
    scope_id = models.UUIDField()
    scope_version = models.PositiveIntegerField()
    scope_fingerprint = models.CharField(max_length=64)
    concept_id = models.UUIDField()
    concept_version = models.PositiveIntegerField()
    concept_fingerprint = models.CharField(max_length=64)
    template_id = models.CharField(max_length=80)
    template_version = models.PositiveIntegerField()
    template_hash = models.CharField(max_length=64)
    input_snapshot = models.JSONField()
    content_fingerprint = models.CharField(max_length=64)
    unresolved_items = models.JSONField(default=list)
    revision = models.PositiveIntegerField(default=1)
    idempotency_key = models.CharField(max_length=160)
    request_hash = models.CharField(max_length=64)
    creation_response = models.JSONField(default=dict)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("plan_id", "version"), name="search_plan_version"),
                       models.UniqueConstraint(fields=("project_id", "created_by", "idempotency_key"), name="search_plan_request_key")]


class PlanChild(Immutable):
    # FK identifies the immutable plan version, so cross-project/version children cannot be mixed.
    plan = models.ForeignKey(SearchPlan, on_delete=models.CASCADE)

    class Meta:
        abstract = True


class SearchBlock(PlanChild):
    block_key = models.CharField(max_length=80)
    facet_type = models.CharField(max_length=40)
    label = models.CharField(max_length=240)
    source_spans = models.JSONField()
    term_refs = models.JSONField()
    relation_hypotheses = models.JSONField(default=list)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("plan", "block_key"), name="search_block_key")]


class SearchPlanTask(PlanChild):
    task_key = models.CharField(max_length=80)
    purpose = models.CharField(max_length=240)
    required_blocks = models.JSONField()
    optional_variant_refs = models.JSONField(default=list)
    logical_ast = models.JSONField()
    filters = models.JSONField(default=dict)
    exclusions = models.JSONField(default=list)
    output_partition = models.CharField(max_length=40)
    prerequisites = models.JSONField(default=list)
    expansion_conditions = models.JSONField(default=list)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("plan", "task_key"), name="search_task_key")]


class SearchPlanBatch(PlanChild):
    batch_key = models.CharField(max_length=80)
    task_refs = models.JSONField()
    prerequisites = models.JSONField(default=list)
    activation_conditions = models.JSONField(default=list)
    status = models.CharField(max_length=24, default="planned")

    class Meta:
        constraints = [models.UniqueConstraint(fields=("plan", "batch_key"), name="search_batch_key")]
