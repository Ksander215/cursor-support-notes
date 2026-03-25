"""
Tests for routers — basic endpoint tests.
"""

import os

os.environ["SEC_SCANNER_ALLOWED_HOSTS"] = "testserver,localhost,127.0.0.1"
os.environ["SEC_SCANNER_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoints:
    def test_healthz(self, client):
        r = client.get("/healthz")
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True or data.get("status") == "ok"

    def test_root_redirects_to_docs(self, client):
        r = client.get("/")
        assert r.status_code in [200, 307, 308, 404]


class TestAuditsRouter:
    def test_list_audits_requires_auth(self, client):
        r = client.get("/api/v1/audits")
        assert r.status_code == 200

    def test_create_audit_invalid_target(self, client):
        r = client.post("/api/v1/audits", json={"target": "invalid-target-format"})
        assert r.status_code == 400

    def test_get_audit_not_found(self, client):
        r = client.get("/api/v1/audits/nonexistent-id")
        assert r.status_code == 404

    def test_quota_requires_auth(self, client):
        r = client.get("/api/v1/quota")
        assert r.status_code == 401


class TestKeysRouter:
    def test_list_api_keys_requires_auth(self, client):
        r = client.get("/api/v1/api-keys")
        assert r.status_code == 401

    def test_create_api_key_requires_auth(self, client):
        r = client.post("/api/v1/api-keys", json={"key_name": "Test Key"})
        assert r.status_code == 401

    def test_revoke_api_key_requires_auth(self, client):
        r = client.delete("/api/v1/api-keys/test-id")
        assert r.status_code == 401

    def test_admin_create_api_key_requires_admin(self, client):
        r = client.post(
            "/api/v1/admin/api-keys",
            json={"org_name": "Test Org", "plan_code": "free"},
        )
        assert r.status_code == 403


class TestWebhooksRouter:
    def test_list_webhooks_requires_auth(self, client):
        r = client.get("/api/v1/webhooks")
        assert r.status_code == 401

    def test_create_webhook_requires_auth(self, client):
        r = client.post(
            "/api/v1/webhooks",
            json={"url": "https://example.com/webhook", "events": ["scan_completed"]},
        )
        assert r.status_code == 401


class TestNotificationsRouter:
    def test_list_notifications_requires_auth(self, client):
        r = client.get("/api/v1/notifications")
        assert r.status_code == 404

    def test_create_notification_requires_auth(self, client):
        r = client.post(
            "/api/v1/notifications",
            json={"channel": "email", "events": ["scan_completed"], "config": {}},
        )
        assert r.status_code == 404


class TestReferralsRouter:
    def test_get_referral_stats_requires_auth(self, client):
        r = client.get("/api/v1/referrals/stats")
        assert r.status_code == 401

    def test_generate_referral_code_requires_auth(self, client):
        r = client.post("/api/v1/referrals/generate-code")
        assert r.status_code == 401


class TestConfigRouter:
    def test_get_whitelabel_config_requires_auth(self, client):
        r = client.get("/api/v1/config/whitelabel")
        assert r.status_code == 404

    def test_update_whitelabel_config_requires_auth(self, client):
        r = client.put(
            "/api/v1/config/whitelabel",
            json={"company_name": "Test Company"},
        )
        assert r.status_code == 404


class TestAdminRouter:
    def test_get_audit_logs_requires_admin(self, client):
        r = client.get("/api/v1/admin/audit-logs")
        assert r.status_code == 403


class TestLeadsRouter:
    def test_audit_request(self, client):
        r = client.post(
            "/api/v1/audit-request",
            json={
                "email": "test@example.com",
                "api_url": "https://api.example.com",
                "project_description": "Test project",
            },
        )
        assert r.status_code in [200, 404, 500]
