import tempfile
import unittest
from pathlib import Path

from aiohttp import CookieJar, web
from aiohttp.test_utils import TestClient, TestServer

from core.api.hospice.admin_api import register_admin_routes
from core.api.hospice.auth import (
    AuthError,
    HospiceAuthStore,
    build_auth_middleware,
    hash_password,
    register_auth_routes,
    verify_password,
)


SECRET = "test-secret-key-with-more-than-thirty-two-characters"


def make_store(tmp_path, **config):
    return HospiceAuthStore(
        str(tmp_path / "auth.db"),
        SECRET,
        {
            "enabled": True,
            "admin_username": "admin",
            "admin_password": "admin-test-password",
            "max_failed_attempts": 2,
            "lock_seconds": 60,
            **config,
        },
    )


class HospiceAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_restart_preserves_sessions(self):
        store = make_store(self.temp_path)
        tokens = store.issue_tokens(store.authenticate("admin", "admin-test-password"))
        restarted = make_store(self.temp_path)
        self.assertEqual(restarted.verify_access_token(tokens["access_token"]).role, "admin")
        user, renewed = restarted.refresh(tokens["refresh_token"])
        self.assertEqual(user.role, "admin")
        self.assertEqual(restarted.verify_access_token(renewed["access_token"]).role, "admin")

    def test_password_is_hashed_and_verified(self):
        encoded = hash_password("correct-password")
        self.assertNotIn("correct-password", encoded)
        self.assertTrue(verify_password("correct-password", encoded))
        self.assertFalse(verify_password("wrong-password", encoded))

    def test_config_admin_can_login_and_is_not_a_normal_role(self):
        store = make_store(self.temp_path)
        admin = store.authenticate("admin", "admin-test-password")
        self.assertEqual(admin.role, "admin")
        with self.assertRaises(ValueError):
            store.create_user("second-admin", "correct-password", "管理员", "admin")

    def test_login_tokens_and_password_reset(self):
        store = make_store(self.temp_path)
        created = store.create_user("patient01", "correct-password", "张阿姨", "patient")
        store.update_user(created.username, patient_ids=["AA:BB:CC:DD:EE:FF"])
        user = store.authenticate("patient01", "correct-password")
        tokens = store.issue_tokens(user)
        verified = store.verify_access_token(tokens["access_token"])
        self.assertEqual(verified.username, "patient01")
        self.assertTrue(store.can_access_patient(verified, "AA:BB:CC:DD:EE:FF"))
        self.assertFalse(store.can_access_patient(verified, "11:22:33:44:55:66"))
        store.update_user("patient01", password="new-correct-password")
        with self.assertRaises(AuthError):
            store.verify_access_token(tokens["access_token"])

    def test_failed_logins_lock_account(self):
        store = make_store(self.temp_path)
        store.create_user("family01", "correct-password", "家属", "family")
        self.assertIsNone(store.authenticate("family01", "bad-password"))
        self.assertIsNone(store.authenticate("family01", "bad-password"))
        with self.assertRaisesRegex(AuthError, "锁定"):
            store.authenticate("family01", "correct-password")

    def test_pairing_access_can_be_revoked(self):
        store = make_store(self.temp_path)
        user = store.create_user("family01", "correct-password", "家属", "family")
        store.add_pairing_access(user, "family-binding-1", "patient-1")
        self.assertTrue(store.can_access_patient(user, "patient-1"))
        self.assertTrue(store.owns_pairing(user, "family-binding-1", "patient-1"))
        store.remove_pairing_access("family-binding-1", "patient-1")
        self.assertFalse(store.can_access_patient(user, "patient-1"))


class HospiceAdminApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        config = {
            "enabled": True,
            "admin_username": "admin",
            "admin_password": "admin-test-password",
        }
        self.store = HospiceAuthStore(str(Path(self.temp_dir.name) / "auth.db"), SECRET, config)
        app = web.Application(middlewares=[build_auth_middleware(self.store, config)])
        register_auth_routes(app, self.store, config)
        register_admin_routes(app, self.store)
        self.client = TestClient(TestServer(app), cookie_jar=CookieJar(unsafe=True))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.temp_dir.cleanup()

    async def test_independent_sessions(self):
        for role in ("patient", "family", "clinician"):
            self.store.create_user(role, "correct-password", role, role)
            r = await self.client.post("/api/auth/login", headers={"X-Hospice-Role": role}, json={"username": role, "password": "correct-password"})
            self.assertEqual(r.status, 200)
            self.assertTrue(r.cookies[f"hospice_refresh_{role}"]["httponly"])
            self.assertEqual(int(r.cookies[f"hospice_refresh_{role}"]["max-age"]), 30 * 86400)
        for role in ("patient", "family", "clinician"):
            r = await self.client.get("/api/auth/me", headers={"Referer": f"http://localhost/{role}/index.html"})
            self.assertEqual((await r.json())["user"]["role"], role)
        await self.client.post("/api/auth/logout", headers={"X-Hospice-Role": "family"})
        for role, status in (("family", 401), ("patient", 200), ("clinician", 200)):
            r = await self.client.get("/api/auth/me", headers={"X-Hospice-Role": role})
            self.assertEqual(r.status, status)

    async def test_admin_creates_and_updates_account(self):
        response = await self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin-test-password"},
        )
        self.assertEqual(response.status, 200)
        response = await self.client.post(
            "/api/admin/users",
            json={
                "username": "patient01",
                "display_name": "张阿姨",
                "password": "patient-password",
                "role": "patient",
                "patient_ids": ["patient-device-1"],
            },
        )
        self.assertEqual(response.status, 200)
        payload = await response.json()
        self.assertEqual(payload["users"][0]["patient_ids"], ["patient-device-1"])

        response = await self.client.patch(
            "/api/admin/users/patient01",
            json={"enabled": False},
        )
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["users"][0]["enabled"], 0)


if __name__ == "__main__":
    unittest.main()
