from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import connection, close_old_connections
from django.test import TestCase, TransactionTestCase
from config.errors import BusinessError
from modules.retrieval.decomposition import decompose, load_template, validate_structure
from modules.retrieval.services import create_plan, list_plans
from modules.retrieval.models import SearchPlan
from modules.execution.models import Event
from tests.scenarios.test_m1_1 import fixture


class StructureContracts(TestCase):
    def test_invalid_references_cycles_and_partitions_are_atomic(self):
        user = get_user_model().objects.create_user("schema-owner")
        project = fixture(user)
        data = {"expected_revision": 0, **list_plans(user, project.id)["inputs"]}
        original, _ = create_plan(user, project.id, data, "base")
        template = load_template()
        content = decompose(original["input_snapshot"], template)
        mutations = [lambda c: c["tasks"][0]["required_blocks"].append("missing"),
                     lambda c: c["tasks"][0]["prerequisites"].append("Q01"),
                     lambda c: c["tasks"][0].update(output_partition="unknown"),
                     lambda c: c["batches"][0].update(status="active"),
                     lambda c: c["tasks"][0]["logical_ast"].update(op="NOT"),
                     lambda c: c.pop("tasks"),
                     lambda c: c["blocks"][0].pop("term_refs"),
                     lambda c: c["batches"][0]["prerequisites"].append("Q01"),
                     lambda c: c["tasks"][0]["prerequisites"].append("M01")]
        for i, mutate in enumerate(mutations):
            broken = deepcopy(content); mutate(broken)
            with self.assertRaises(BusinessError): validate_structure(broken, template)
            with patch("modules.retrieval.services.decompose", return_value=broken):
                with self.assertRaises(BusinessError): create_plan(user, project.id, data, f"bad-{i}")
        self.assertEqual(SearchPlan.objects.count(), 1)
        self.assertEqual(Event.objects.filter(event_type="SearchPlanDraftCreated").count(), 1)


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locking")
class ConcurrentPlanContracts(TransactionTestCase):
    def test_same_key_race_creates_one_complete_draft_and_event(self):
        user = get_user_model().objects.create_user("race-plan-owner")
        project = fixture(user)
        data = {"expected_revision": 0, **list_plans(user, project.id)["inputs"]}
        barrier = Barrier(2)
        def work(_):
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=user.pk)
                barrier.wait(timeout=10)
                return create_plan(actor, project.id, data, "same-key")
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor: results = list(executor.map(work, range(2)))
        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(sorted(r[1] for r in results), [False, True])
        self.assertEqual(SearchPlan.objects.count(), 1)
        self.assertEqual(Event.objects.filter(event_type="SearchPlanDraftCreated").count(), 1)
