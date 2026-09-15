from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch
import uuid
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import TestCase, Client, override_settings
from django.utils import timezone
from config.errors import BusinessError
from modules.identity.models import AuditRecord, CredentialToken, ProjectMembership
from modules.identity.services import issue_token, redeem_token
from modules.projects.models import Project, ResearchConstraint, DependencyEdge, CreateRequest, MutationRecord, WorkflowProjection, WorkflowState
from modules.projects.services import rebuild_projection, ANSWER_FIELDS
from modules.execution.models import Event, Outbox, Inbox, Task
from modules.execution.services import complete_task
from modules.knowledge.models import ConceptVersion


class M0Scenarios(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user("owner", password="old-password-123")
        self.researcher = User.objects.create_user("researcher", password="old-password-123")
        self.reviewer = User.objects.create_user("reviewer", password="old-password-123")
        self.admin = User.objects.create_user("administrator", password="old-password-123", is_staff=True)
        self.client.force_login(self.owner)
        self.created = self.client.post("/api/v1/projects", {"name": "M0", "direction": "Cancer", "core_keywords": ["ferroptosis"], "expected_revision": 0}, content_type="application/json", HTTP_IDEMPOTENCY_KEY="create").json()
        self.project = Project.objects.get(pk=self.created["id"])
        ProjectMembership.objects.create(project=self.project, user=self.researcher, role="researcher")
        ProjectMembership.objects.create(project=self.project, user=self.reviewer, role="reviewer")
        self.base = f"/api/v1/projects/{self.project.id}"

    def post(self, suffix, data, key=None, client=None):
        return (client or self.client).post(self.base + suffix, data, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()))

    def details(self):
        details = self.client.get(self.base + "/scope").json()["scope"]["details"]
        details["answers"] = {key: "complete" for key in ANSWER_FIELDS}
        details["answers"].update(years="2020—2026", include="experimental", exclude="reviews")
        for candidate in details["candidates"]: candidate["decision"] = "accepted"
        details["semantic_review"] = "Manually checked terms, dates and boundaries."
        return details

    def test_scope_restores_fresh_session_history_and_linked_invalidation(self):
        details = self.details()
        confirmed = self.post("/scope", {"action": "confirm", "details": details, "expected_revision": 1})
        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        old = ResearchConstraint.objects.get(project=self.project, version=1)
        self.assertEqual(ConceptVersion.objects.filter(scope_id=old.id).count(), 1)
        concept = ConceptVersion.objects.get(scope_id=old.id)
        concept_edge = DependencyEdge.objects.get(source_id=old.id, target_id=concept.id)
        child, grandchild, unrelated = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        edge = DependencyEdge.objects.create(project=self.project, source_id=old.id, target_id=child, target_kind="fixture", approval_content={"approved": True})
        nested = DependencyEdge.objects.create(project=self.project, source_id=child, target_id=grandchild, target_kind="fixture")
        independent = DependencyEdge.objects.create(project=self.project, source_id=unrelated, target_id=uuid.uuid4(), target_kind="fixture")
        response = self.post("/scope", {"action": "edit", "expected_revision": 2})
        self.assertEqual(response.status_code, 200)
        fresh = Client(); fresh.force_login(self.owner)
        restored = fresh.get(self.base + "/scope").json()
        self.assertEqual(restored["scope"]["details"], details)
        self.assertEqual(len(restored["history"]), 2)
        old.refresh_from_db(); edge.refresh_from_db(); nested.refresh_from_db(); independent.refresh_from_db()
        self.assertEqual(old.status, "confirmed"); self.assertEqual(old.details, details)
        self.assertEqual(edge.approval_content, {"approved": True})
        self.assertEqual(edge.applicability, "needs_revalidation"); self.assertEqual(nested.applicability, "needs_revalidation")
        self.assertEqual(independent.applicability, "current")
        concept_edge.refresh_from_db()
        self.assertEqual(concept_edge.applicability, "needs_revalidation")
        old.direction = "overwrite"
        with self.assertRaises(ValueError): old.save()

    def test_scope_incomplete_duplicate_conflict_and_provenance_bypasses(self):
        self.assertEqual(self.post("/scope", {"action": "confirm", "expected_revision": 1}).status_code, 422)
        for change in ({"candidates": []}, {"answers": {**self.details()["answers"], "years": "2027—2020"}}, {"answers": {**self.details()["answers"], "exclude": "experimental"}}):
            response = self.post("/scope", {"action": "confirm", "details": {**self.details(), **change}, "expected_revision": 1})
            self.assertEqual(response.status_code, 422, response.content)
        details = self.details(); details["conflicts"] = [{"id": "conflict-1", "description": "ambiguous", "resolution": ""}]
        self.assertEqual(self.post("/scope", {"action": "save", "details": details, "expected_revision": 1}).status_code, 200)
        details["conflicts"] = []
        self.assertEqual(self.post("/scope", {"action": "confirm", "details": details, "expected_revision": 2}).status_code, 422)

    def test_two_sessions_revision_and_actor_scoped_idempotency(self):
        second = Client(); second.force_login(self.researcher)
        payload = {"action": "save", "details": self.details(), "expected_revision": 1}
        first = self.post("/scope", payload, "shared")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(self.post("/scope", payload, "shared")["Idempotent-Replay"], "true")
        self.assertEqual(self.post("/scope", {**payload, "action": "confirm"}, "shared").status_code, 409)
        self.assertEqual(self.post("/scope", payload, "different", second).status_code, 409)
        self.assertEqual(self.post("/scope", {**payload, "expected_revision": 2}, "shared", second).status_code, 200)
        self.assertEqual(MutationRecord.objects.filter(key="shared").count(), 2)

    def test_roles_all_reads_mutations_and_file_denial(self):
        task = Task.objects.create(project_id=self.project.id, kind="projection.rebuild", input_fingerprint="0" * 64, target_version_id=self.project.constraints.first().id)
        paths = ["/status", "/scope", "/navigation", "/models/status", f"/tasks/{task.id}"]
        for actor in (self.admin, self.reviewer, self.researcher):
            self.client.force_login(actor)
            expected = 404 if actor == self.admin else 200
            for suffix in paths: self.assertEqual(self.client.get(self.base + suffix).status_code, expected, suffix)
            items = self.client.get("/api/v1/projects").json()["items"]
            self.assertEqual(len(items), 0 if actor == self.admin else 1)
            self.assertEqual(self.client.get(self.base + "/files/" + str(uuid.uuid4())).status_code, 404)
            self.assertEqual(self.client.get(self.base + "/members").status_code, 404)
        for actor in (self.admin, self.reviewer):
            self.client.force_login(actor)
            for suffix in ("/scope", "/gold/evaluate", "/retrieval/compile", "/retrieval/manual-runs", "/materials/import-summary", "/evidence", "/candidates", "/decisions", "/contributions/validate", "/projection/rebuild", f"/tasks/{task.id}/retry"):
                self.assertEqual(self.post(suffix, {"expected_revision": 1, "action": "save"}).status_code, 404, suffix)

    def test_projection_rebuild_replays_watermark_without_duplicate_effects(self):
        self.post("/scope", {"action": "save", "expected_revision": 1})
        Event.objects.create(stream_id=self.project.id, stream_seq=3, event_type="UnrelatedEvent", payload={})
        WorkflowProjection.objects.filter(project=self.project).delete()
        first = rebuild_projection(self.project)
        initial = (first.step_states, first.source_stream_watermarks)
        count = Inbox.objects.count()
        second = rebuild_projection(self.project)
        self.assertEqual(initial, (second.step_states, second.source_stream_watermarks))
        self.assertEqual(Inbox.objects.count(), count)
        self.assertEqual(second.source_stream_watermarks[str(self.project.id)], 3)

    def test_retry_runs_local_handler_and_rejects_stale_or_paid_results(self):
        scope = self.project.constraints.first()
        task = Task.objects.create(project_id=self.project.id, kind="projection.rebuild", status="failed", input_fingerprint="0" * 64, target_version_id=scope.id)
        response = self.post(f"/tasks/{task.id}/retry", {"expected_revision": 1})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "succeeded")
        task.refresh_from_db()
        with self.assertRaises(BusinessError): complete_task(task.id, task.fencing_token - 1)
        task.status = "failed"; task.kind = "paid.model"; task.save()
        self.assertEqual(self.post(f"/tasks/{task.id}/retry", {"expected_revision": 2}).status_code, 422)
        task.kind = "projection.rebuild"; task.target_version_id = uuid.uuid4(); task.save()
        self.assertEqual(self.post(f"/tasks/{task.id}/retry", {"expected_revision": 2}).status_code, 409)

    def test_create_fault_after_each_write_rolls_back_and_can_retry(self):
        factories = [Project, ResearchConstraint, DependencyEdge, WorkflowProjection, WorkflowState, Event, Outbox, AuditRecord, Inbox, CreateRequest]
        for index, model in enumerate(factories):
            original = model.save
            def fail_after(instance, *args, **kwargs):
                original(instance, *args, **kwargs)
                raise RuntimeError("injected")
            payload = {"name": "rollback-" + str(index), "direction": "D", "core_keywords": ["K"], "expected_revision": 0}
            before = Project.objects.count()
            with patch.object(model, "save", new=fail_after):
                response = self.client.post("/api/v1/projects", payload, content_type="application/json", HTTP_IDEMPOTENCY_KEY="fault-" + str(index))
                self.assertEqual(response.status_code, 500)
            self.assertEqual(Project.objects.count(), before)
            self.assertFalse(CreateRequest.objects.filter(key="fault-" + str(index)).exists())
            response = self.client.post("/api/v1/projects", payload, content_type="application/json", HTTP_IDEMPOTENCY_KEY="fault-" + str(index))
            self.assertEqual(response.status_code, 201)

    def test_invite_reset_expiry_replay_reissue_revocation_and_audit(self):
        first = issue_token(self.admin, "invited", "invite")
        issued = issue_token(self.admin, "invited", "invite")
        with self.assertRaises(BusinessError): redeem_token(first["token"], "Valid-New-Password-42")
        with self.assertRaises(BusinessError): redeem_token(issued["token"], "weak")
        redeem_token(issued["token"], "Valid-New-Password-42")
        user = get_user_model().objects.get(username="invited")
        self.assertTrue(user.is_active); self.assertFalse(ProjectMembership.objects.filter(user=user).exists())
        with self.assertRaises(BusinessError): redeem_token(issued["token"], "Valid-New-Password-42")
        client = Client(); client.force_login(user)
        reset = issue_token(self.admin, "invited", "reset")
        redeem_token(reset["token"], "Another-New-Password-42")
        self.assertFalse(client.get("/api/v1/session/login").json()["authenticated"])
        expired = issue_token(self.admin, "invited", "reset")
        CredentialToken.objects.filter(user=user, consumed_at=None).update(expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(BusinessError): redeem_token(expired["token"], "Another-New-Password-42")
        self.assertNotIn(issued["token"], str(list(CredentialToken.objects.values())))
        self.assertNotIn(issued["token"], str(list(AuditRecord.objects.values())))
        self.assertTrue(AuditRecord.objects.filter(action="credential.redeemed.invite", actor=user).exists())

    def test_login_failure_structured_and_throttled_valid_login_reset(self):
        client = Client()
        for _ in range(4): self.assertEqual(client.post("/api/v1/session/login", {"username": "owner", "password": "bad"}).status_code, 403)
        for _ in range(6): self.assertEqual(client.post("/api/v1/session/login", {"username": "owner", "password": "old-password-123"}).status_code, 200)
        for _ in range(5): self.assertEqual(client.post("/api/v1/session/login", {"username": "owner", "password": "bad"}).json()["error"]["code"], "LOGIN_FAILED")
        self.assertEqual(client.post("/api/v1/session/login", {"username": "owner", "password": "bad"}).status_code, 429)

    def test_malformed_inputs_and_forged_approvals_never_grant_formal_status(self):
        oversized = self.post("/scope", {"expected_revision": 1, "action": "save", "padding": "x" * (256 * 1024)})
        self.assertEqual(oversized.status_code, 413)
        for malformed in ([], {"expected_revision": True}, {"expected_revision": 1, "total_hits": -1}, {"expected_revision": 1, "total_hits": "NaN"}):
            self.assertEqual(self.post("/retrieval/manual-runs", malformed).status_code, 422)
        ast = {"type": "term", "field": "title", "value": "x"}
        for _ in range(10): ast = {"type": "not", "child": ast}
        self.assertEqual(self.post("/retrieval/compile", {"expected_revision": 1, "ast": ast}).status_code, 422)
        result = self.post("/contributions/validate", {"expected_revision": 1, "approval_reviewers": ["a", "b"], "license_valid": True, "confirmed": True}).json()
        self.assertFalse(result["valid"]); self.assertFalse(result["reward_created"])

    def test_review_invalid_inputs_and_inactive_removal(self):
        for suffix, data in (("/evidence", {"status": []}), ("/evidence", {"status": {}}), ("/retrieval/compile", {"platform": []}), ("/retrieval/manual-runs", {"executed_at": "not-a-date"})):
            response = self.post(suffix, {"expected_revision": 1, **data})
            self.assertEqual(response.status_code, 422, response.content)
        self.researcher.is_active = False
        self.researcher.save()
        response = self.post("/members", {"expected_revision": 1, "user_id": self.researcher.pk, "role": "remove"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(ProjectMembership.objects.filter(project=self.project, user=self.researcher).exists())

    def test_retry_key_cannot_replay_another_task(self):
        scope = self.project.constraints.first()
        tasks = [Task.objects.create(project_id=self.project.id, kind="projection.rebuild", status="failed", input_fingerprint="0" * 64, target_version_id=scope.id) for _ in range(2)]
        self.assertEqual(self.post(f"/tasks/{tasks[0].id}/retry", {"expected_revision": 1}, "same-task-key").status_code, 200)
        self.assertEqual(self.post(f"/tasks/{tasks[1].id}/retry", {"expected_revision": 1}, "same-task-key").status_code, 409)
        tasks[1].refresh_from_db()
        self.assertEqual(tasks[1].status, "failed")

    def test_old_formal_state_is_exploratory_without_changing_storage(self):
        state = WorkflowState.objects.get(project=self.project)
        original = {"candidates": [{"status": "decision_ready", "qualified": True, "human_verified": True}]}
        state.data = deepcopy(original); state.save()
        payload = self.client.get(self.base + "/status").json()["domain_workflow"]
        self.assertFalse(payload["candidates"][0]["qualified"])
        self.assertEqual(payload["candidates"][0]["status"], "legacy_unverified")
        state.refresh_from_db(); self.assertEqual(state.data, original)

    def test_errors_log_correlation_without_exception_material(self):
        from config.errors import unexpected_error
        with self.assertLogs("ai4s.errors", level="ERROR") as logs:
            response = unexpected_error(RuntimeError("restricted-material-secret"))
        self.assertIn(response["error"]["trace_id"], str(logs.output))
        self.assertNotIn("restricted-material-secret", str(logs.output))
