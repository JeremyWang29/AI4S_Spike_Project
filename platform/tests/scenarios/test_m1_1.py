from copy import deepcopy
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from modules.projects.models import Project, ResearchConstraint
from modules.projects.services import initial_details, ANSWER_FIELDS, scope_command
from modules.retrieval.models import SearchPlan, SearchBlock, SearchPlanTask, SearchPlanBatch
from modules.retrieval.services import list_plans
from modules.execution.models import Event, Outbox

TITLE = "PSMB5通过LSD1-PRMT5抑制铁死亡介导食管鳞癌放疗抵抗的研究"


def fixture(user, title=TITLE, keywords=None):
    project = Project.objects.create(owner=user, name=title)
    details = initial_details(keywords or ["PSMB5", "铁死亡"])
    details["answers"] = {key: "人工确认" for key in ANSWER_FIELDS}
    details["answers"].update(years="2020—2026", include="原始研究", exclude="综述")
    for key in ("object", "mechanism", "method", "outcome", "context"):
        details["research_fields"][key] = {"status": "answered", "selected": [], "text": details["answers"][key]}
    details["boundary"].update(start="2020-01-01", end="2026-12-31")
    details["semantic_review"] = "人工词义核对"
    for item in details["candidates"]: item["decision"] = "accepted"
    ResearchConstraint.objects.create(project=project, direction=title, core_keywords=keywords or ["PSMB5", "铁死亡"], details=details)
    scope_command(project, None, {"action": "confirm", "details": details})
    return project


class SearchPlanScenarios(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("plan-owner")
        self.project = fixture(self.user)
        self.client.force_login(self.user)
        self.path = f"/api/v1/projects/{self.project.id}/search-plans"
        self.body = {"expected_revision": 0, **list_plans(self.user, self.project.id)["inputs"]}

    def post(self, body=None, key="draft-one"):
        return self.client.post(self.path, body or self.body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)

    def test_psmb5_saved_draft_refresh_sources_and_partition(self):
        response = self.post()
        self.assertEqual(response.status_code, 201, response.content)
        plan = response.json()
        self.assertEqual(plan["status"], "draft")
        self.assertEqual(set(b["block_key"] for b in plan["blocks"]), set("ABCDEFG"))
        self.assertEqual(plan["batches"][0]["task_refs"], ["Q01", "Q02", "Q11"])
        self.assertTrue(all(b["status"] == "planned" for b in plan["batches"]))
        self.assertTrue(all(not t["filters"] and not t["exclusions"] for t in plan["tasks"]))
        self.assertTrue(any(t["output_partition"] == "cross_disease_supplement" for t in plan["tasks"]))
        g = next(b for b in plan["blocks"] if b["block_key"] == "G")
        self.assertEqual({r.get("subclass") for r in g["term_refs"]}, {"resistance", "sensitivity"})
        self.assertTrue(any(item.get("marker") == "LSD1-PRMT5" for item in plan["unresolved_items"]))
        client = Client(); client.force_login(self.user)
        self.assertEqual(client.get(f'/api/v1/search-plans/{plan["id"]}').json(), plan)
        self.assertEqual(client.get(self.path).json()["items"][0], plan)
        self.assertEqual(Event.objects.filter(event_type="SearchPlanDraftCreated").count(), 1)
        self.assertEqual(Outbox.objects.count(), 1)
        self.assertEqual(self.post().json(), plan)
        self.assertEqual(SearchPlan.objects.count(), 1)
        self.assertEqual(self.post({**self.body, "research_title": "different"}).status_code, 409)
        for model in (SearchPlan, SearchBlock, SearchPlanTask, SearchPlanBatch):
            with self.assertRaises(ValueError): model.objects.first().save()

    def test_version_permission_and_scope_change_history(self):
        original = self.post().json()
        invalid = deepcopy(self.body); invalid["concept_ref"]["version"] += 1
        self.assertEqual(self.post(invalid, "bad-version").status_code, 409)
        other = get_user_model().objects.create_user("outsider", is_staff=True)
        self.client.force_login(other)
        self.assertEqual(self.client.get(self.path).status_code, 404)
        self.assertEqual(self.client.get(f'/api/v1/search-plans/{original["id"]}').status_code, 404)
        self.assertEqual(self.post().status_code, 404)
        self.client.force_login(self.user)
        scope_command(self.project, None, {"action": "edit"})
        self.assertEqual(self.post(key="after-edit").status_code, 409)
        current = self.client.get(f'/api/v1/search-plans/{original["id"]}').json()
        self.assertEqual(current["applicability"], "needs_revalidation")
        self.assertEqual(current["content_fingerprint"], original["content_fingerprint"])
        self.assertEqual(SearchPlan.objects.get().applicability, "needs_revalidation")
        self.assertEqual(self.post().json(), original)

    def test_generic_conflict_unknown_acronym_and_no_approval_input(self):
        other = fixture(self.user, "TP53调控肺癌自噬XYZ", ["PSMB5", "食管鳞癌", "XYZ"])
        self.path = f"/api/v1/projects/{other.id}/search-plans"
        self.body = {"expected_revision": 0, **list_plans(self.user, other.id)["inputs"]}
        for field in ("confirmed", "approved", "active", "blocks"):
            self.assertEqual(self.post({**self.body, field: True}, field).status_code, 422)
        plan = self.post().json()
        self.assertNotIn("Q11", [t["task_key"] for t in plan["tasks"]])
        codes = {i["code"] for i in plan["unresolved_items"]}
        self.assertTrue({"TERM_MEANING_UNRESOLVED", "RESEARCH_OBJECT_CONFLICT", "TITLE_KEYWORD_CONFLICT"} <= codes)

    def test_partial_failure_rolls_back_all_objects_and_event(self):
        with patch("modules.retrieval.services.append_event", side_effect=RuntimeError("injected")):
            self.assertEqual(self.post().status_code, 500)
        for model in (SearchPlan, SearchBlock, SearchPlanTask, SearchPlanBatch, Event, Outbox): self.assertEqual(model.objects.count(), 0)
        self.assertEqual(self.post().status_code, 201)

    def test_title_override_and_fixed_boolean_semantics(self):
        plan = self.post({**self.body, "research_title": TITLE + "：XYZ机制"}, "override").json()
        self.assertEqual(plan["input_snapshot"]["title_source"], "research_title_override")
        self.assertEqual(plan["input_snapshot"]["research_title"], TITLE + "：XYZ机制")
        def expr(node):
            return node["ref"] if node["type"] == "block" else [node["op"], *map(expr, node["children"])]
        expected = {"Q01": ["AND", "D", "E", ["OR", "F", "G"]], "Q02": ["AND", "A", "D"], "Q11": ["AND", "A", "B", "C", "D", "E", ["OR", "F", "G"]]}
        for saved in (plan, self.client.get(f'/api/v1/search-plans/{plan["id"]}').json()):
            for task in saved["tasks"]:
                if task["task_key"] in expected: self.assertEqual(expr(task["logical_ast"]), expected[task["task_key"]])
            unknown = next(b for b in saved["blocks"] if b["label"] == "XYZ")
            self.assertTrue(any(s["source"] == "research_title_override" for s in unknown["source_spans"]))

    def test_unknown_provenance_long_label_and_generic_partition(self):
        project = fixture(self.user, "XYZ介导肺癌", ["XYZ", "肺癌"])
        self.path = f"/api/v1/projects/{project.id}/search-plans"
        self.body = {"expected_revision": 0, **list_plans(self.user, project.id)["inputs"]}
        plan = self.post().json()
        block = next(b for b in plan["blocks"] if b["label"] == "XYZ")
        self.assertTrue({"accepted_term", "user_term"} <= {r["origin"] for r in block["term_refs"]})
        self.assertGreaterEqual(len(block["source_spans"]), 3)
        for task in plan["tasks"]:
            if block["block_key"] in task["required_blocks"]: self.assertEqual(task["output_partition"], "cross_disease_supplement")
        response = self.post({**self.body, "research_title": "X" * 241}, "long")
        self.assertEqual(response.status_code, 201, response.content)
        long_block = next(b for b in response.json()["blocks"] if b["label"] == "X" * 240)
        self.assertEqual(long_block["source_spans"][0]["fragment"], "X" * 241)

    def test_rejected_concepts_and_additional_blocks_are_explicit(self):
        from modules.retrieval.decomposition import decompose, load_template
        plan = self.post().json()
        snapshot = deepcopy(plan["input_snapshot"])
        snapshot["concept"]["decisions"] = [{"term": "PSMB5", "decision": "rejected"}]
        content = decompose(snapshot, load_template())
        self.assertFalse(any("A" in task["required_blocks"] for task in content["tasks"]))
        self.assertTrue(any(i["code"] == "CONCEPT_DECISION_CONFLICT" for i in content["unresolved_items"]))
        snapshot = deepcopy(plan["input_snapshot"])
        snapshot["concept"]["terms"].append("自噬")
        content = decompose(snapshot, load_template())
        self.assertTrue(any(i["code"] == "BLOCK_TASK_PLACEMENT_PENDING" and "autophagy" in i["block_refs"] for i in content["unresolved_items"]))
