import uuid
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(name="Event", fields=[("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)), ("stream_id", models.UUIDField(db_index=True)), ("stream_seq", models.PositiveBigIntegerField()), ("event_type", models.CharField(max_length=120)), ("payload", models.JSONField()), ("occurred_at", models.DateTimeField(auto_now_add=True))], options={"constraints": [models.UniqueConstraint(fields=("stream_id", "stream_seq"), name="event_stream_sequence")]}),
        migrations.CreateModel(name="Task", fields=[("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)), ("project_id", models.UUIDField(db_index=True)), ("kind", models.CharField(max_length=80)), ("status", models.CharField(default="accepted", max_length=24)), ("input_fingerprint", models.CharField(max_length=64)), ("target_version_id", models.UUIDField()), ("fencing_token", models.PositiveBigIntegerField(default=1)), ("lease_until", models.DateTimeField(null=True)), ("created_at", models.DateTimeField(auto_now_add=True))]),
        migrations.CreateModel(name="Inbox", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("consumer", models.CharField(max_length=120)), ("event_id", models.UUIDField()), ("processed_at", models.DateTimeField(auto_now_add=True))], options={"constraints": [models.UniqueConstraint(fields=("consumer", "event_id"), name="consumer_event_once")]}),
        migrations.CreateModel(name="Outbox", fields=[("event", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, primary_key=True, serialize=False, to="execution.event")), ("delivered_at", models.DateTimeField(null=True)), ("attempts", models.PositiveIntegerField(default=0))]),
    ]
