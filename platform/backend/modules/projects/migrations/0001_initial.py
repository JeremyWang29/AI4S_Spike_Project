import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="Project", fields=[
        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
        ("name", models.CharField(max_length=200)), ("revision", models.PositiveIntegerField(default=1)),
        ("required_dependencies", models.JSONField(default=dict)), ("created_at", models.DateTimeField(auto_now_add=True)),
        ("updated_at", models.DateTimeField(auto_now=True)),
        ("owner", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
    ]),
    migrations.CreateModel(name="WorkflowState", fields=[
        ("project", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name="workflow", serialize=False, to="projects.project")),
        ("data", models.JSONField(default=dict)), ("updated_at", models.DateTimeField(auto_now=True)),
    ]),
    migrations.CreateModel(name="MutationRecord", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("key", models.CharField(max_length=160)), ("action", models.CharField(max_length=120)),
        ("request_hash", models.CharField(max_length=64)), ("response", models.JSONField()),
        ("created_at", models.DateTimeField(auto_now_add=True)),
        ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="projects.project")),
    ], options={"constraints": [models.UniqueConstraint(fields=("project", "key"), name="project_idempotency_key")]}),]
