from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, Client
from django.contrib.auth import get_user_model
from modules.core import fingerprint
from modules.projects.models import Project, ResearchConstraint, MutationRecord, DependencyEdge
from modules.execution.models import Event


class M0MigrationTests(TransactionTestCase):
    def test_historical_receipt_backfill_replays_without_new_mutation(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [("projects", "0002_project_entry")]
        try:
            executor.migrate(before)
            apps = executor.loader.project_state(before).apps
            user = apps.get_model("auth", "User").objects.create(username="migration-owner")
            project = apps.get_model("projects", "Project").objects.create(owner_id=user.pk, name="historical", revision=2)
            apps.get_model("projects", "ResearchConstraint").objects.create(project=project, direction="old", core_keywords=["keyword"])
            body = {"expected_revision": 1, "query_id": "old-query", "total_hits": 10}
            original = {"id": "old-result", "qualified": True, "project_revision": 2}
            apps.get_model("projects", "MutationRecord").objects.create(project=project, key="old-key", action="retrieval.manual_run", request_hash=fingerprint({"action": "retrieval.manual_run", "body": body}), response=original)
            project_id, user_id = project.pk, user.pk
        finally:
            MigrationExecutor(connection).migrate(latest)
        receipt = MutationRecord.objects.get(project_id=project_id, key="old-key")
        self.assertEqual(receipt.actor_id, user_id)
        scope = ResearchConstraint.objects.get(project_id=project_id)
        self.assertEqual(scope.details["candidates"][0]["term"], "keyword")
        self.assertTrue(DependencyEdge.objects.filter(source_id=project_id, target_id=scope.id).exists())
        client = Client(); client.force_login(get_user_model().objects.get(pk=user_id))
        count = Event.objects.count()
        response = client.post(f"/api/v1/projects/{project_id}/retrieval/manual-runs", body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="old-key")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.headers["Idempotent-Replay"], "true")
        self.assertFalse(response.json()["qualified"])
        self.assertEqual(Project.objects.get(pk=project_id).revision, 2)
        self.assertEqual(Event.objects.count(), count)
        receipt.refresh_from_db(); self.assertEqual(receipt.response, original)
