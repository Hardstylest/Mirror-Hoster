"""MirrorStream backend API tests."""
import os
import uuid
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend .env parsing
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

API = f"{BASE_URL}/api"
ADMIN_EMAIL = "admin@mirrorstream.com"
ADMIN_PASSWORD = "Admin@1234"


# ---- Fixtures ----
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def user_creds():
    email = f"TEST_user_{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPass@123"
    r = requests.post(f"{API}/auth/register", json={"name": "Test User", "email": email, "password": password})
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    data = r.json()
    return {"email": email, "password": password, "token": data["access_token"], "id": data["user"]["id"]}


@pytest.fixture(scope="session")
def hosts(admin_token):
    r = requests.get(f"{API}/hosts", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    return r.json()


# ---- Auth ----
class TestAuth:
    def test_me_no_token(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_me_with_token(self, admin_token):
        r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        d = r.json()
        assert d["email"] == ADMIN_EMAIL
        assert d["role"] == "admin"

    def test_login_bad_password(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": f"noone_{uuid.uuid4().hex[:6]}@x.com", "password": "bad"})
        assert r.status_code == 401

    def test_register_and_role(self, user_creds):
        r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {user_creds['token']}"})
        assert r.status_code == 200
        assert r.json()["role"] == "user"


# ---- Hosts ----
class TestHosts:
    def test_seeded_hosts(self, hosts):
        names = {h["name"] for h in hosts}
        assert "DoodStream" in names
        assert "VOE" in names

    def test_non_admin_cannot_create_host(self, user_creds):
        r = requests.post(f"{API}/hosts",
                          json={"name": "TEST_x", "domain": "x.com", "default_rate": 1.0, "tiers": []},
                          headers={"Authorization": f"Bearer {user_creds['token']}"})
        assert r.status_code == 403

    def test_admin_create_update_delete_host(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        payload = {"name": "TEST_HOST", "domain": "test.example", "default_rate": 3.0,
                   "tiers": [{"name": "T1", "rate": 10, "countries": ["US"]}]}
        r = requests.post(f"{API}/hosts", json=payload, headers=h)
        assert r.status_code == 200
        hid = r.json()["id"]
        # update
        payload["default_rate"] = 4.0
        r = requests.put(f"{API}/hosts/{hid}", json=payload, headers=h)
        assert r.status_code == 200
        assert r.json()["default_rate"] == 4.0
        # delete
        r = requests.delete(f"{API}/hosts/{hid}", headers=h)
        assert r.status_code == 200


# ---- Mirrors ----
class TestMirrors:
    def test_create_and_list_mirror(self, user_creds, hosts):
        h = {"Authorization": f"Bearer {user_creds['token']}"}
        dood = next(x for x in hosts if x["name"] == "DoodStream")
        voe = next(x for x in hosts if x["name"] == "VOE")
        payload = {
            "title": "TEST_Movie",
            "description": "desc",
            "links": [
                {"host_id": dood["id"], "embed_url": "https://doodstream.com/e/testabc"},
                {"host_id": voe["id"], "embed_url": "https://voe.sx/e/testxyz"},
            ],
        }
        r = requests.post(f"{API}/mirrors", json=payload, headers=h)
        assert r.status_code == 200, r.text
        m = r.json()
        assert m["title"] == "TEST_Movie"
        assert m["slug"]
        assert len(m["links"]) == 2
        pytest.mirror_id = m["id"]
        pytest.mirror_slug = m["slug"]

        r = requests.get(f"{API}/mirrors", headers=h)
        assert r.status_code == 200
        assert any(mm["id"] == m["id"] for mm in r.json())

    def test_dashboard_stats(self, user_creds):
        r = requests.get(f"{API}/stats/dashboard",
                         headers={"Authorization": f"Bearer {user_creds['token']}"})
        assert r.status_code == 200
        d = r.json()
        for k in ["total_mirrors", "total_views", "links_online", "links_offline", "links_pending"]:
            assert k in d

    def test_embed_public_no_auth_sorting_ES(self):
        r = requests.get(f"{API}/embed/{pytest.mirror_slug}?country=ES")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["country_code"] == "ES"
        hosts = data["hosts"]
        assert len(hosts) == 2
        # VOE tier for ES = 12, Dood tier for ES = 11 -> VOE first
        assert hosts[0]["host_name"] == "VOE"
        assert hosts[0]["rate"] == 12.0
        assert hosts[1]["host_name"] == "DoodStream"
        assert hosts[1]["rate"] == 11.0

    def test_embed_public_no_auth_sorting_US(self):
        r = requests.get(f"{API}/embed/{pytest.mirror_slug}?country=US")
        assert r.status_code == 200
        data = r.json()
        hosts = data["hosts"]
        assert hosts[0]["host_name"] == "VOE"
        assert hosts[0]["rate"] == 40.0
        assert hosts[1]["host_name"] == "DoodStream"
        assert hosts[1]["rate"] == 33.0

    def test_mirror_stats(self, user_creds):
        r = requests.get(f"{API}/stats/mirror/{pytest.mirror_id}",
                         headers={"Authorization": f"Bearer {user_creds['token']}"})
        assert r.status_code == 200
        d = r.json()
        assert "timeline" in d and "countries" in d and "per_host" in d
        assert d["total_views"] >= 2  # from two embed calls above

    def test_check_mirror(self, user_creds):
        r = requests.post(f"{API}/mirrors/{pytest.mirror_id}/check",
                          headers={"Authorization": f"Bearer {user_creds['token']}"},
                          timeout=60)
        assert r.status_code == 200
        d = r.json()
        for l in d["links"]:
            assert l["status"] in ("online", "offline")
            assert l["last_checked"]

    def test_update_mirror(self, user_creds, hosts):
        dood = next(x for x in hosts if x["name"] == "DoodStream")
        payload = {"title": "TEST_Movie_updated", "description": "d2",
                   "links": [{"host_id": dood["id"], "embed_url": "https://doodstream.com/e/testabc"}]}
        r = requests.put(f"{API}/mirrors/{pytest.mirror_id}", json=payload,
                         headers={"Authorization": f"Bearer {user_creds['token']}"})
        assert r.status_code == 200
        assert r.json()["title"] == "TEST_Movie_updated"

    def test_delete_mirror(self, user_creds):
        r = requests.delete(f"{API}/mirrors/{pytest.mirror_id}",
                            headers={"Authorization": f"Bearer {user_creds['token']}"})
        assert r.status_code == 200
        r = requests.get(f"{API}/mirrors/{pytest.mirror_id}",
                         headers={"Authorization": f"Bearer {user_creds['token']}"})
        assert r.status_code == 404


# ---- Admin ----
class TestAdmin:
    def test_admin_stats(self, admin_token):
        r = requests.get(f"{API}/admin/stats", headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        for k in ["total_users", "total_mirrors", "total_hosts", "total_views", "offline_links"]:
            assert k in r.json()

    def test_admin_users(self, admin_token):
        r = requests.get(f"{API}/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        users = r.json()
        assert any(u["email"] == ADMIN_EMAIL for u in users)
        for u in users:
            assert "mirror_count" in u
            assert "role" in u

    def test_non_admin_forbidden(self, user_creds):
        r = requests.get(f"{API}/admin/stats", headers={"Authorization": f"Bearer {user_creds['token']}"})
        assert r.status_code == 403
        r = requests.get(f"{API}/admin/users", headers={"Authorization": f"Bearer {user_creds['token']}"})
        assert r.status_code == 403
