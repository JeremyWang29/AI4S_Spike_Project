import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('knowledge', '0001_initial')]

    operations = [migrations.CreateModel(
        name='GraphTerm',
        fields=[
            ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
            ('project_id', models.UUIDField(null=True, blank=True, db_index=True)),
            ('graph_version', models.CharField(max_length=120)),
            ('concept_id', models.CharField(max_length=200)),
            ('source_position', models.CharField(max_length=500)),
            ('term', models.CharField(max_length=200)),
            ('definition', models.TextField(blank=True)),
            ('parent_keyword', models.CharField(max_length=200)),
            ('relation', models.CharField(max_length=24)),
            ('license', models.CharField(max_length=200)),
            ('external_sharing_allowed', models.BooleanField(default=False)),
            ('active', models.BooleanField(default=True)),
        ],
        options={'constraints': [models.UniqueConstraint(fields=('project_id', 'graph_version', 'concept_id', 'parent_keyword', 'relation'), name='graph_term_version_identity')]},
    )]
