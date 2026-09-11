import uuid
from django.db import models


class Task(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_id = models.UUIDField(db_index=True)
    kind = models.CharField(max_length=80)
    status = models.CharField(max_length=24, default="accepted")
    input_fingerprint = models.CharField(max_length=64)
    target_version_id = models.UUIDField()
    fencing_token = models.PositiveBigIntegerField(default=1)
    lease_until = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "execution"


class Event(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stream_id = models.UUIDField(db_index=True)
    stream_seq = models.PositiveBigIntegerField()
    event_type = models.CharField(max_length=120)
    payload = models.JSONField()
    occurred_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        app_label = "execution"
        constraints = [models.UniqueConstraint(fields=("stream_id", "stream_seq"), name="event_stream_sequence")]


class Outbox(models.Model):
    event = models.OneToOneField(Event, primary_key=True, on_delete=models.PROTECT)
    delivered_at = models.DateTimeField(null=True)
    attempts = models.PositiveIntegerField(default=0)
    class Meta: app_label = "execution"


class Inbox(models.Model):
    consumer = models.CharField(max_length=120)
    event_id = models.UUIDField()
    processed_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        app_label = "execution"
        constraints = [models.UniqueConstraint(fields=("consumer", "event_id"), name="consumer_event_once")]
