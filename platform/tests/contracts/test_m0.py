from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import os
from pathlib import Path
import subprocess
import sys
from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, Client
from config.errors import BusinessError
from modules.identity.services import issue_token, redeem_token
from modules.identity.models import CredentialToken
from modules.projects.models import Project


class DeploymentContractTests(TestCase):
    def test_nondevelopment_missing_secret_fails_closed(self):
        env = {**os.environ, "AI4S_ENV": "acceptance", "AI4S_SECRET_KEY": ""}
        backend = Path(__file__).resolve().parents[2] / "backend"
        result = subprocess.run(
            [sys.executable, "manage.py", "check"],
            cwd=backend, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("AI4S_SECRET_KEY", result.stderr)

    def test_creation_of_test_accounts_is_development_only(self):
        from django.core.management import call_command, CommandError
        with self.settings(AI4S_ENV="acceptance"):
            with self.assertRaises(CommandError): call_command("create_test_user", "forbidden", password="test-password-123")


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locking; SQLite functional tests are separate")
class PostgreSQLConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.owner = get_user_model().objects.create_user("race-owner", password="password-1234")
        self.admin = get_user_model().objects.create_user("race-admin", is_staff=True)

    def parallel(self, work):
        barrier = Barrier(2)
        def run(index):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return work(index)
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, range(2)))

    def test_same_actor_create_key_serializes_complete_project(self):
        owner_id = self.owner.pk
        def work(_):
            client = Client(); client.force_login(get_user_model().objects.get(pk=owner_id))
            response = client.post("/api/v1/projects", {"name": "race", "direction": "D", "core_keywords": ["K"], "expected_revision": 0}, content_type="application/json", HTTP_IDEMPOTENCY_KEY="race")
            return response.status_code, response.json()["id"]
        results = self.parallel(work)
        self.assertEqual([status for status, _ in results], [201, 201])
        self.assertEqual(results[0][1], results[1][1]); self.assertEqual(Project.objects.count(), 1)

    def test_single_token_two_redemptions_exactly_once(self):
        issued = issue_token(self.admin, "race-invite", "invite")
        def work(_):
            try: redeem_token(issued["token"], "Valid-Password-1234"); return "ok"
            except BusinessError as exc: return exc.code
        self.assertCountEqual(self.parallel(work), ["ok", "CREDENTIAL_DENIED"])
        self.assertEqual(CredentialToken.objects.filter(consumed_at__isnull=False).count(), 1)

    def test_same_revision_scope_writes_one_winner(self):
        client = Client(); client.force_login(self.owner)
        project = client.post("/api/v1/projects", {"name": "P", "direction": "D", "core_keywords": ["K"], "expected_revision": 0}, content_type="application/json", HTTP_IDEMPOTENCY_KEY="base").json()
        owner_id = self.owner.pk
        def work(index):
            client = Client(); client.force_login(get_user_model().objects.get(pk=owner_id))
            return client.post(f"/api/v1/projects/{project['id']}/scope", {"action": "save", "expected_revision": 1}, content_type="application/json", HTTP_IDEMPOTENCY_KEY=f"write-{index}").status_code
        self.assertCountEqual(self.parallel(work), [200, 409])
    def test_login_session_is_visible_to_waiting_revocation(self):
        from threading import Event as Signal
        from unittest.mock import patch
        from django.test import RequestFactory
        from django.db import transaction
        from django.contrib.auth.models import AnonymousUser
        from django.contrib.sessions.backends.db import SessionStore
        from django.contrib.sessions.models import Session
        from modules.identity import views
        from modules.identity.services import revoke_sessions
        persisted, release, attempted, revoked = Signal(), Signal(), Signal(), Signal()
        original = views.audit
        def pause_audit(actor, action, object_id):
            if action == "session.login":
                self.assertTrue(Session.objects.filter(session_key=request.session.session_key).exists())
                persisted.set()
                if not release.wait(10): raise TimeoutError("test release")
            return original(actor, action, object_id)
        request = RequestFactory().post("/api/v1/session/login", {"username": self.owner.username, "password": "password-1234"})
        request.session = SessionStore(); request.user = AnonymousUser(); request._dont_enforce_csrf_checks = True
        def signing_in():
            close_old_connections()
            try: return views.session_login(request).status_code
            finally: close_old_connections()
        def revoking():
            close_old_connections()
            try:
                attempted.set()
                with transaction.atomic():
                    user = get_user_model().objects.select_for_update().get(pk=self.owner.pk)
                    revoke_sessions(user)
                revoked.set()
            finally: close_old_connections()
        with patch.object(views, "audit", side_effect=pause_audit), ThreadPoolExecutor(max_workers=2) as pool:
            login_future = pool.submit(signing_in)
            try:
                self.assertTrue(persisted.wait(10))
                revoke_future = pool.submit(revoking)
                self.assertTrue(attempted.wait(10))
                self.assertFalse(revoked.wait(0.2), "revocation must wait for login's account lock")
            finally: release.set()
            self.assertEqual(login_future.result(timeout=10), 200)
            revoke_future.result(timeout=10)
        self.assertFalse(Session.objects.filter(session_key=request.session.session_key).exists())
