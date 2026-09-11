from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.test import override_settings
from modules.projects.models import CreateRequest, Project, ResearchConstraint, WorkflowProjection
from modules.execution.models import Task
import uuid
from unittest.mock import patch

class ProjectApiScenarioTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user("owner", password="secret")
        self.other = get_user_model().objects.create_user("other", password="secret")
        self.project = Project.objects.create(name="铁死亡介导癌症放疗抵抗", owner=self.owner,
            required_dependencies={"literature": "qualified", "patent": "awaiting_manual_return"})
    def test_project_isolation_t01(self):
        self.client.force_login(self.other)
        response = self.client.get(f"/api/v1/projects/{self.project.id}/status")
        self.assertEqual(response.status_code, 404); self.assertEqual(response.json()["error"]["code"], "PROJECT_NOT_FOUND")
    def test_independent_dependency_status_s01(self):
        self.client.force_login(self.owner)
        data = self.client.get(f"/api/v1/projects/{self.project.id}/status").json()
        self.assertEqual(data["dependencies"]["literature"], "qualified")
        self.assertEqual(data["dependencies"]["patent"], "awaiting_manual_return")
    def test_gold_api_exact_boundary(self):
        self.client.force_login(self.owner)
        checks = {"platform_rule_valid": True, "syntax_capability_valid": True,
                  "semantic_equivalence_valid": True, "not_exclusion_regression_passed": True,
                  "actual_execution_verified": True}
        payload = {"expected_revision": 1, "scope": "literature", "tuning": {"tp": 17, "fp": 3, "fn": 3, "tn": 2},
                   "acceptance": {"tp": 17, "fp": 3, "fn": 3, "tn": 2}, "checks": checks}
        response = self.client.post(f"/api/v1/projects/{self.project.id}/gold/evaluate", payload, content_type="application/json", HTTP_IDEMPOTENCY_KEY="gold-1")
        self.assertEqual(response.status_code, 200); self.assertTrue(response.json()["qualified"])

    def test_gold_cannot_qualify_without_all_formal_checks(self):
        self.client.force_login(self.owner)
        payload = {"expected_revision": 1, "scope": "literature",
                   "tuning": {"tp": 17, "fp": 3, "fn": 3, "tn": 2},
                   "acceptance": {"tp": 17, "fp": 3, "fn": 3, "tn": 2},
                   "checks": {"platform_rule_valid": True}}
        response = self.client.post(f"/api/v1/projects/{self.project.id}/gold/evaluate", payload,
                                    content_type="application/json", HTTP_IDEMPOTENCY_KEY="gold-incomplete")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["qualified"])

    def test_gold_requires_idempotency_and_revision_t02(self):
        self.client.force_login(self.owner)
        url = f"/api/v1/projects/{self.project.id}/gold/evaluate"
        self.assertEqual(self.client.post(url, {}, content_type="application/json").json()["error"]["code"], "IDEMPOTENCY_KEY_REQUIRED")
        self.assertEqual(self.client.post(url, {}, content_type="application/json", HTTP_IDEMPOTENCY_KEY="x").json()["error"]["code"], "EXPECTED_REVISION_REQUIRED")

    @override_settings(AI4S_PLATFORM_RULES={"demo": {"version": 1, "field_map": {"title": "TI"}, "operators": ["AND", "OR"], "verified": True, "license_verified": True}})
    def test_m1_retrieval_import_workflow_and_replay(self):
        self.client.force_login(self.owner)
        compile_payload = {"expected_revision": 1, "platform": "demo", "scope": "literature", "kind": "coarse_search",
                           "ast": {"type": "term", "field": "title", "value": "ferroptosis"}}
        url = f"/api/v1/projects/{self.project.id}/retrieval/compile"
        first = self.client.post(url, compile_payload, content_type="application/json", HTTP_IDEMPOTENCY_KEY="q1")
        self.assertEqual(first.status_code, 200); self.assertEqual(first.json()["status"], "ready")
        replay = self.client.post(url, compile_payload, content_type="application/json", HTTP_IDEMPOTENCY_KEY="q1")
        self.assertEqual(replay["Idempotent-Replay"], "true")
        changed = {**compile_payload, "platform": "other"}
        self.assertEqual(self.client.post(url, changed, content_type="application/json", HTTP_IDEMPOTENCY_KEY="q1").status_code, 409)
        query_id = first.json()["id"]
        run = self.client.post(f"/api/v1/projects/{self.project.id}/retrieval/manual-runs",
            {"expected_revision": 2, "query_id": query_id, "platform": "demo", "total_hits": 2, "complete_export": True},
            content_type="application/json", HTTP_IDEMPOTENCY_KEY="run1").json()
        imported = self.client.post(f"/api/v1/projects/{self.project.id}/materials/import-summary",
            {"expected_revision": 3, "run_id": run["id"], "file_hash": "a" * 64, "parsed_count": 2, "errors": []},
            content_type="application/json", HTTP_IDEMPOTENCY_KEY="import1").json()
        self.assertEqual(imported["coverage"], "complete")

    def test_m2_evidence_candidate_and_decision_matrix(self):
        self.client.force_login(self.owner)
        evidence = self.client.post(f"/api/v1/projects/{self.project.id}/evidence",
            {"expected_revision": 1, "source_record_id": "src1", "snapshot_id": "snap1", "page": 7,
             "excerpt_hash": "b" * 64, "status": "supported", "human_verified": True},
            content_type="application/json", HTTP_IDEMPOTENCY_KEY="ev1").json()
        candidate = self.client.post(f"/api/v1/projects/{self.project.id}/candidates",
            {"expected_revision": 2, "question": "Does ferroptosis mediate resistance?", "gap_types": ["evidence_content", "method"],
             "slice_version": "slice1", "evidence_ids": [evidence["id"]], "primary_search_applicable": True,
             "required_followups_complete": True, "three_checks_complete": True, "expert_reviewed": True, "evidence_sufficient": True},
            content_type="application/json", HTTP_IDEMPOTENCY_KEY="cand1").json()
        self.assertEqual(candidate["status"], "eligible")
        decision = self.client.post(f"/api/v1/projects/{self.project.id}/decisions",
            {"expected_revision": 3, "candidate_id": candidate["id"], "scope_version": "scope1", "snapshot_id": "snap1", "limitations": ["hypothesis"]},
            content_type="application/json", HTTP_IDEMPOTENCY_KEY="decision1").json()
        self.assertEqual(decision["status"], "decision_ready")

    def test_evidence_states_distinguish_absent_insufficient_and_conflicting(self):
        self.client.force_login(self.owner)
        url = f"/api/v1/projects/{self.project.id}/evidence"
        absent = self.client.post(url, {"expected_revision": 1, "snapshot_id": "snap1", "search_report_id": "search1",
            "status": "not_retrieved", "human_verified": True}, content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="evidence-absent")
        self.assertEqual(absent.status_code, 200)
        self.assertEqual(absent.json()["claim_status"], "not_retrieved")
        insufficient = self.client.post(url, {"expected_revision": 2, "source_record_id": "src1", "snapshot_id": "snap1",
            "page": 3, "excerpt_hash": "d" * 64, "status": "insufficient", "human_verified": True},
            content_type="application/json", HTTP_IDEMPOTENCY_KEY="evidence-insufficient")
        self.assertEqual(insufficient.json()["claim_status"], "insufficient")
        conflicting = self.client.post(url, {"expected_revision": 3, "source_record_id": "src2", "snapshot_id": "snap1",
            "page": 8, "excerpt_hash": "e" * 64, "status": "conflicting", "human_verified": True},
            content_type="application/json", HTTP_IDEMPOTENCY_KEY="evidence-conflicting")
        self.assertEqual(conflicting.json()["claim_status"], "conflicting")

    def test_invalid_gap_taxonomy_is_rejected(self):
        self.client.force_login(self.owner)
        response = self.client.post(f"/api/v1/projects/{self.project.id}/candidates",
            {"expected_revision": 1, "question": "q", "gap_types": ["mechanism"]}, content_type="application/json", HTTP_IDEMPOTENCY_KEY="bad-gap")
        self.assertEqual(response.status_code, 422); self.assertEqual(response.json()["error"]["code"], "INVALID_GAP_TAXONOMY")

    def test_m3_reward_once_and_noncontribution_no_reward(self):
        self.client.force_login(self.owner); url = f"/api/v1/projects/{self.project.id}/contributions/validate"
        base = {"expected_revision": 1, "subset": ["n1", "n2"], "description": "verified subset", "confirmed": True,
                "approval_reviewers": ["r1", "r2"], "current_overlap": "0.20", "submit_threshold": "0.30", "license_valid": True,
                "publication_type": "eligible_contribution"}
        first = self.client.post(url, base, content_type="application/json", HTTP_IDEMPOTENCY_KEY="pub1").json()
        self.assertTrue(first["valid"]); self.assertTrue(first["reward_created"])
        replay = self.client.post(url, base, content_type="application/json", HTTP_IDEMPOTENCY_KEY="pub1").json()
        self.assertEqual(replay["eligibility_id"], first["eligibility_id"])
        ordinary = {**base, "expected_revision": 2, "publication_type": "ordinary"}
        result = self.client.post(url, ordinary, content_type="application/json", HTTP_IDEMPOTENCY_KEY="pub2").json()
        self.assertFalse(result["reward_created"]); self.assertIsNone(result["eligibility_id"])

    def test_m4_model_and_task_status_are_project_isolated(self):
        self.client.force_login(self.owner)
        model = self.client.get(f"/api/v1/projects/{self.project.id}/models/status").json()
        self.assertEqual(model["status"], "UNCONFIGURED")
        task = Task.objects.create(project_id=self.project.id, kind="analysis", input_fingerprint="c" * 64, target_version_id=uuid.uuid4())
        self.assertEqual(self.client.get(f"/api/v1/projects/{self.project.id}/tasks/{task.id}").json()["status"], "accepted")
        other_project = Project.objects.create(name="other", owner=self.other)
        self.assertEqual(self.client.get(f"/api/v1/projects/{other_project.id}/tasks/{task.id}").status_code, 404)

    def test_session_and_csrf_business_codes_t20(self):
        strict = Client(enforce_csrf_checks=True)
        anonymous = strict.get(f"/api/v1/projects/{self.project.id}/status")
        self.assertEqual(anonymous.status_code, 403); self.assertEqual(anonymous.json()["error"]["code"], "NOT_AUTHENTICATED")
        login_response = strict.post("/api/v1/session/login", {"username": "owner", "password": "secret"})
        self.assertEqual(login_response.status_code, 403); self.assertEqual(login_response.json()["error"]["code"], "CSRF_FAILED")

    def test_session_login_issues_csrf_cookie_and_accepts_token_t20(self):
        strict = Client(enforce_csrf_checks=True)
        bootstrap = strict.get("/api/v1/session/login")
        token = bootstrap.cookies["csrftoken"].value
        response = strict.post("/api/v1/session/login", {"username": "owner", "password": "secret"},
                               HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["authenticated"])

    def test_project_collection_creates_atomic_v011_entry_s17_t22(self):
        self.client.force_login(self.owner)
        payload = {"expected_revision": 0, "name": " 放疗抵抗机制 ", "direction": "铁死亡与放疗抵抗",
                   "core_keywords": [" ferroptosis ", "放疗", "FERROPTOSIS", " "]}
        response = self.client.post("/api/v1/projects", payload, content_type="application/json",
                                    HTTP_IDEMPOTENCY_KEY="create-1")
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["name"], "放疗抵抗机制")
        self.assertEqual(data["core_keywords"], ["ferroptosis", "放疗"])
        self.assertEqual(data["scope_version"], 1)
        self.assertEqual(data["workflow"]["current_step"], "scope")
        project = Project.objects.get(pk=data["id"])
        self.assertEqual(project.constraints.get().status, "draft")
        self.assertEqual(project.projection.step_states["project"], "complete")
        self.assertEqual(project.workflow.data["queries"], [])

        replay = self.client.post("/api/v1/projects", payload, content_type="application/json",
                                  HTTP_IDEMPOTENCY_KEY="create-1")
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(replay["Idempotent-Replay"], "true")
        self.assertEqual(replay.json()["id"], data["id"])
        self.assertEqual(CreateRequest.objects.filter(user=self.owner, key="create-1").count(), 1)

    def test_project_collection_validates_and_isolates_users(self):
        self.client.force_login(self.owner)
        invalid = self.client.post("/api/v1/projects",
            {"expected_revision": 0, "name": " ", "direction": " ", "core_keywords": [" "]},
            content_type="application/json", HTTP_IDEMPOTENCY_KEY="invalid")
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.json()["error"]["code"], "PROJECT_INPUT_INVALID")

        created = self.client.post("/api/v1/projects",
            {"expected_revision": 0, "name": "P", "direction": "D", "core_keywords": ["K"]},
            content_type="application/json", HTTP_IDEMPOTENCY_KEY="shared-key")
        self.assertEqual(created.status_code, 201)
        owner_ids = {item["id"] for item in self.client.get("/api/v1/projects").json()["items"]}
        self.assertIn(created.json()["id"], owner_ids)

        self.client.force_login(self.other)
        other = self.client.post("/api/v1/projects",
            {"expected_revision": 0, "name": "Other", "direction": "D", "core_keywords": ["K"]},
            content_type="application/json", HTTP_IDEMPOTENCY_KEY="shared-key")
        self.assertEqual(other.status_code, 201)
        other_ids = {item["id"] for item in self.client.get("/api/v1/projects").json()["items"]}
        self.assertNotIn(created.json()["id"], other_ids)

    def test_project_create_idempotency_conflict_and_rollback(self):
        self.client.force_login(self.owner)
        base = {"expected_revision": 0, "name": "P", "direction": "D", "core_keywords": ["K"]}
        self.client.post("/api/v1/projects", base, content_type="application/json", HTTP_IDEMPOTENCY_KEY="same")
        changed = {**base, "direction": "changed"}
        conflict = self.client.post("/api/v1/projects", changed, content_type="application/json",
                                    HTTP_IDEMPOTENCY_KEY="same")
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["error"]["code"], "IDEMPOTENCY_CONFLICT")

        before = Project.objects.count()
        with patch("modules.projects.views.Outbox.objects.create", side_effect=RuntimeError("outbox failed")):
            with self.assertRaises(RuntimeError):
                self.client.post("/api/v1/projects", {**base, "name": "Rollback"},
                                 content_type="application/json", HTTP_IDEMPOTENCY_KEY="rollback")
        self.assertEqual(Project.objects.count(), before)
        self.assertFalse(ResearchConstraint.objects.filter(project__name="Rollback").exists())
        self.assertFalse(WorkflowProjection.objects.filter(project__name="Rollback").exists())
