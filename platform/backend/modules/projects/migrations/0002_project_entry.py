import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("projects", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ResearchConstraint",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("version", models.PositiveIntegerField(default=1)),
                ("status", models.CharField(default="draft", max_length=24)),
                ("direction", models.TextField()),
                ("core_keywords", models.JSONField(default=list)),
                ("details", models.JSONField(default=dict)),
                ("confirmed_at", models.DateTimeField(null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="constraints", to="projects.project")),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("project", "version"), name="project_constraint_version")]},
        ),
        migrations.CreateModel(
            name="WorkflowProjection",
            fields=[
                ("project", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name="projection", serialize=False, to="projects.project")),
                ("current_step", models.CharField(default="scope", max_length=40)),
                ("step_states", models.JSONField(default=dict)),
                ("blocking_items", models.JSONField(default=list)),
                ("source_stream_watermarks", models.JSONField(default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="CreateRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=160)),
                ("request_hash", models.CharField(max_length=64)),
                ("response", models.JSONField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("user", "key"), name="user_project_create_key")]},
        ),
    ]
