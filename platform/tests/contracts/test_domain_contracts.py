from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest import TestCase

from config.errors import BusinessError
from modules.analysis import SliceVersion, apply_template, upgrade_slice, analytical_status
from modules.assets import Contribution
from modules.entitlements import Ledger, REWARD_SECONDS
from modules.evaluation import Hit, combine, GoldGroup, Evaluation
from modules.execution import ReliableTask, Budget
from modules.identity import AccessFacts
from modules.models import ModelPolicy, prepare_request, route_status
from modules.operations import Journal, Deletion
from modules.research import CandidateGate
from modules.retrieval import Term, Bool, PlatformRule, canonical, compile_query, check_gates


class EvaluationContractTests(TestCase):
    checks = {
        "platform_rule_valid": True,
        "syntax_capability_valid": True,
        "semantic_equivalence_valid": True,
        "not_exclusion_regression_passed": True,
        "actual_execution_verified": True,
    }

    def test_three_state_truth_table_s04(self):
        self.assertEqual(combine("OR", ["hit", "unknown"]), Hit.HIT)
        self.assertEqual(combine("OR", ["miss", "unknown"]), Hit.UNKNOWN)
        self.assertEqual(combine("AND", ["miss", "unknown"]), Hit.MISS)
        self.assertEqual(combine("AND", ["hit", "unknown"]), Hit.UNKNOWN)

    def test_exact_point_85_and_fifty_are_valid_s06_t06(self):
        tuning = GoldGroup("tuning", 17, 3, 3, 2)
        acceptance = GoldGroup("acceptance", 17, 3, 3, 2)
        result = Evaluation("literature", tuning, acceptance, self.checks)
        self.assertEqual(tuning.recall, Decimal("0.85")); self.assertTrue(result.qualified)

    def test_missing_formal_check_blocks_approval(self):
        tuning = GoldGroup("tuning", 17, 3, 3, 2)
        acceptance = GoldGroup("acceptance", 17, 3, 3, 2)
        result = Evaluation("literature", tuning, acceptance, {**self.checks, "actual_execution_verified": False})
        self.assertFalse(result.qualified)
        self.assertIn("actual_execution_verified", {b.message.split(": ", 1)[-1] for b in result.blockers()})

    def test_49_rounding_unknown_and_missing_label_block_t06(self):
        cases = [
            Evaluation("literature", GoldGroup("t", 17, 3, 3, 1), GoldGroup("a", 17, 3, 3, 1), {}),
            Evaluation("literature", GoldGroup("t", 8496, 1004, 1504, 1), GoldGroup("a", 17, 3, 3, 2), {}),
            Evaluation("literature", GoldGroup("t", 24, 0, 0, 1, 1), GoldGroup("a", 24, 0, 0, 1), {}),
            Evaluation("literature", GoldGroup("t", 25, 0, 0, 0), GoldGroup("a", 25, 0, 0, 0), {}),
        ]
        self.assertTrue(all(not x.qualified for x in cases))


class RetrievalContractTests(TestCase):
    def test_canonical_compilation_and_unverified_block(self):
        ast = Bool("OR", (Term("title", "ferroptosis"), Term("abstract", "radioresistance")))
        rule = PlatformRule("example", 1, {"title": "TI", "abstract": "AB"}, ("OR", "AND"), True, True)
        query, blocker = compile_query(ast, rule)
        self.assertIsNone(blocker); self.assertIn("TI", query); self.assertEqual(canonical(ast)["op"], "OR")
        _, blocker = compile_query(ast, PlatformRule("unknown", 1, {}, (), False, False))
        self.assertEqual(blocker.code, "PLATFORM_RULE_UNVERIFIED")

    def test_coarse_does_not_require_gold_but_formal_does_s02(self):
        facts = {"rule_verified": True, "license_verified": True, "ast_valid": True}
        self.assertEqual(check_gates("coarse_search", facts), [])
        self.assertTrue(check_gates("formal_search", facts))


class ReliabilityContractTests(TestCase):
    def test_stale_worker_and_old_target_s08_t02(self):
        task = ReliableTask("v1", {"query": 1}); old = task.fencing_token; task.retry_lease()
        with self.assertRaises(BusinessError): task.complete(old, {}, "v1")
        task.complete(task.fencing_token, {"ok": True}, "v2"); self.assertEqual(task.status, "historical")

    def test_budget_unknown_is_not_released_t04(self):
        budget = Budget(Decimal("10"), "CNY"); budget.reserve("6"); budget.mark_unknown("6")
        with self.assertRaises(BusinessError): budget.reserve("5")


class PermissionAndModelTests(TestCase):
    def test_intersection_deny_t01(self):
        with self.assertRaises(BusinessError): AccessFacts(True, "owner", True, True, False, True).require("read")
    def test_model_license_and_unconfigured_quality_s14(self):
        policy = ModelPolicy(False, True, False)
        with self.assertRaises(BusinessError): prepare_request(policy, [], "analysis")
        self.assertEqual(route_status(policy), "UNCONFIGURED")


class AssetEntitlementTests(TestCase):
    def test_partial_acceptance_invalidates_consent_s12_s17(self):
        c = Contribution("u", tuple(map(str, range(100))), "d"); c.confirm(); c.approve("r1"); c.approve("r2")
        self.assertTrue(c.publishable(Decimal("0.2"), Decimal("0.3"), True)[0])
        c.modify(tuple(map(str, range(80)))); self.assertEqual(c.publishable(Decimal("0.2"), Decimal("0.3"), True)[1], "CONSENT_STALE")
        c.confirm(); c.approve("r1"); c.approve("r2")
        self.assertEqual(c.publishable(Decimal("0.4"), Decimal("0.3"), True)[1], "OVERLAP_TOO_HIGH")
    def test_unique_reward_fifo_and_pause_s10_s15_s16(self):
        ledger = Ledger(); a = ledger.reward("e1", "asset"); self.assertIs(a, ledger.reward("e1", "asset"))
        b = ledger.reward("e2", "asset"); self.assertTrue(a.active); self.assertFalse(b.active)
        self.assertEqual(ledger.settle("asset", 20 * 86400, True, "day20"), 20 * 86400)
        self.assertEqual(ledger.settle("asset", 20 * 86400, False, "paused"), 0)
        self.assertEqual(a.remaining_seconds, 70 * 86400)


class ResearchAnalysisOperationsTests(TestCase):
    def test_followup_gate_does_not_grant_gold_s06(self):
        gate = CandidateGate("evidence_content", True, True, True, True, True)
        self.assertTrue(gate.eligible)
    def test_unconfigured_analysis_s09_and_independent_slice_s19(self):
        template = SliceVersion("private", {"years": [2020, 2025]}); project = apply_template(template, "p")
        upgraded = upgrade_slice(project, SliceVersion("private", {"years": [2021, 2026]}))
        self.assertNotEqual(project.id, upgraded.id); self.assertEqual(project.definition["years"][0], 2020)
        self.assertFalse(analytical_status(False, {2025: 3})["formal"])
    def test_journal_hash_chain_and_deletion_t08_t09(self):
        journal = Journal(); journal.append("intent", {"id": "x"}, "remote-1"); journal.append("complete", {"id": "x"}, "remote-2")
        self.assertTrue(journal.verify())
        now = datetime.now(timezone.utc); deletion = Deletion(now, now + timedelta(days=10), True)
        self.assertFalse(deletion.content_accessible); self.assertEqual(deletion.purge_at, now + timedelta(days=10)); self.assertTrue(deletion.accepted)
