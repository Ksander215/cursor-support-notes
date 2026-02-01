import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Use a dedicated sqlite file for tests
        os.environ["SEC_SCANNER_DB_PATH"] = os.path.join("data", "test_sec_scanner.db")
        # FastAPI TestClient uses Host: testserver by default (TrustedHostMiddleware)
        os.environ["SEC_SCANNER_ALLOWED_HOSTS"] = "testserver,localhost,127.0.0.1"

        import app

        cls.client = TestClient(app.app)

    def test_healthz(self):
        r = self.client.get("/healthz")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"ok": True})

    def test_root_redirects_to_docs(self):
        r = self.client.get("/", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers.get("location"), "/docs")

    def test_create_audit_stubbed(self):
        with patch("src.sec_scanner.api.enqueue_audit", return_value="test-audit-id"):
            r = self.client.post("/api/v1/audits", json={"target": "example.com", "mode": "safe"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["audit_id"], "test-audit-id")
        self.assertEqual(data["status"], "queued")


if __name__ == "__main__":
    unittest.main()
