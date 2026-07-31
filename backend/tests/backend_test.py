"""MirrorStream backend API tests."""
import os
import re
import uuid
import time
from pathlib import Path

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
credentials_text = Path("/app/memory/test_credentials.md").read_text(encoding="utf-8")
email_match = re.search(r"(?im)^\s*[-*]\s*Email:\s*([^\s]+)", credentials_text)
password_match = re.search(r"(?im)^\s*[-*]\s*Password:\s*([^\s]+)", credentials_text)
if not email_match or not password_match:
    raise RuntimeError("Admin email/password missing from /app/memory/test_credentials.md")
ADMIN_EMAIL = email_match.group(1)
ADMIN_PASSWORD = password_match.group(1)


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


# ---- Offline-check false positive fix (iteration 3) ----
class TestOfflineCheckFix:
    """The check must treat Cloudflare/DDoS-Guard 403 challenges as ONLINE and only
    return offline for definitive signals (404/410 / explicit not-found)."""

    def test_smiooaxb_hosts_stay_online(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        # find SMioOAxb
        r = requests.get(f"{API}/mirrors", headers=headers)
        assert r.status_code == 200
        target = next((m for m in r.json() if m.get("slug") == "SMioOAxb"), None)
        if not target:
            pytest.skip("Seed mirror SMioOAxb not present in this environment")
        r = requests.post(f"{API}/mirrors/{target['id']}/check", headers=headers, timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data["links"]) >= 1
        for l in data["links"]:
            assert l["status"] == "online", (
                f"Cloudflare-protected host wrongly flagged offline: {l.get('embed_url')} -> {l['status']}"
            )
        # embed endpoint should also reflect this
        r = requests.get(f"{API}/embed/SMioOAxb")
        assert r.status_code == 200
        for h in r.json()["hosts"]:
            assert h["status"] != "offline", f"Embed marks online host as offline: {h}"

    def test_genuine_404_marked_offline_but_voe_stays_online(self, admin_token, hosts):
        headers = {"Authorization": f"Bearer {admin_token}"}
        dood = next(x for x in hosts if x["name"] == "DoodStream")
        voe = next(x for x in hosts if x["name"] == "VOE")
        payload = {
            "title": "TEST_OfflineDetect",
            "description": "detect genuine 404 vs cloudflare",
            "links": [
                # genuine 404
                {"host_id": dood["id"],
                 "embed_url": "https://www.google.com/search/thispagedoesnotexist12345"},
                # cloudflare-protected but live
                {"host_id": voe["id"], "embed_url": "https://voe.sx/e/rjseg1wmsyv6"},
            ],
        }
        r = requests.post(f"{API}/mirrors", json=payload, headers=headers)
        assert r.status_code == 200, r.text
        mid = r.json()["id"]
        try:
            r = requests.post(f"{API}/mirrors/{mid}/check", headers=headers, timeout=90)
            assert r.status_code == 200, r.text
            links = {l["embed_url"]: l["status"] for l in r.json()["links"]}
            assert links["https://www.google.com/search/thispagedoesnotexist12345"] == "offline", \
                f"Real 404 must be offline, got {links}"
            assert links["https://voe.sx/e/rjseg1wmsyv6"] == "online", \
                f"Cloudflare voe must stay online, got {links}"
        finally:
            requests.delete(f"{API}/mirrors/{mid}", headers=headers)


# ---- URL Normalization (iteration 4) ----
class TestNormalization:
    """Non-embed host URLs should be auto-converted to /e/ form on create/update."""

    def test_create_mirror_normalizes_urls(self, admin_token, hosts):
        headers = {"Authorization": f"Bearer {admin_token}"}
        dood = next(x for x in hosts if x["name"] == "DoodStream")
        voe = next(x for x in hosts if x["name"] == "VOE")
        payload = {
            "title": "TEST_Normalize",
            "description": "url normalize",
            "links": [
                {"host_id": dood["id"], "embed_url": "https://dsvplay.com/d/f2yosowjefyz"},
                {"host_id": voe["id"], "embed_url": "https://voe.sx/xbelauz0emae"},
            ],
        }
        r = requests.post(f"{API}/mirrors", json=payload, headers=headers)
        assert r.status_code == 200, r.text
        m = r.json()
        mid = m["id"]
        try:
            by_host = {l["host_id"]: l["embed_url"] for l in m["links"]}
            assert by_host[dood["id"]] == "https://dsvplay.com/e/f2yosowjefyz", by_host
            assert by_host[voe["id"]] == "https://voe.sx/e/xbelauz0emae", by_host

            # Update with more variants
            payload2 = {
                "title": "TEST_Normalize",
                "description": "url normalize v2",
                "links": [
                    # already-correct /e/ must stay unchanged
                    {"host_id": dood["id"], "embed_url": "https://dsvplay.com/e/keepme"},
                    # /embed/xyz -> /e/xyz
                    {"host_id": voe["id"], "embed_url": "https://doodstream.com/embed/xyz"},
                ],
            }
            r = requests.put(f"{API}/mirrors/{mid}", json=payload2, headers=headers)
            assert r.status_code == 200, r.text
            m2 = r.json()
            urls = [l["embed_url"] for l in m2["links"]]
            assert "https://dsvplay.com/e/keepme" in urls, urls
            assert "https://doodstream.com/e/xyz" in urls, urls
        finally:
            requests.delete(f"{API}/mirrors/{mid}", headers=headers)

    def test_normalization_edge_cases(self, admin_token, hosts):
        headers = {"Authorization": f"Bearer {admin_token}"}
        dood = next(x for x in hosts if x["name"] == "DoodStream")
        voe = next(x for x in hosts if x["name"] == "VOE")
        payload = {
            "title": "TEST_NormEdges",
            "description": "edges",
            "links": [
                # unknown multi-segment prefix -> unchanged
                {"host_id": dood["id"], "embed_url": "https://dsvplay.com/foo/bar/baz"},
                # bare id single-segment -> gets /e/ prefix; preserve query string
                {"host_id": voe["id"], "embed_url": "https://voe.sx/abc123?autoplay=1"},
            ],
        }
        r = requests.post(f"{API}/mirrors", json=payload, headers=headers)
        assert r.status_code == 200, r.text
        m = r.json()
        mid = m["id"]
        try:
            by_host = {l["host_id"]: l["embed_url"] for l in m["links"]}
            # unknown pattern left alone
            assert by_host[dood["id"]] == "https://dsvplay.com/foo/bar/baz", by_host
            # bare id becomes /e/ AND query preserved
            assert by_host[voe["id"]] == "https://voe.sx/e/abc123?autoplay=1", by_host
        finally:
            requests.delete(f"{API}/mirrors/{mid}", headers=headers)


# ---- Resolved URL / Embed live-domain resolution (iteration 5) ----
class TestResolvedUrl:
    """/embed must resolve DoodStream links to their final redirect domain
    (e.g. dsvplay.com -> playmogo.com) and persist the resolved_url."""

    def test_embed_smiooaxb_returns_canonical_doodstream_domain(self):
        # Iteration 7: DoodStream embed_url is now the canonical user-pasted domain (dsvplay.com)
        r = requests.get(f"{API}/embed/SMioOAxb", timeout=30)
        if r.status_code != 200:
            pytest.skip("Seed mirror SMioOAxb not present")
        data = r.json()
        dood = next((h for h in data["hosts"] if h["host_name"] == "DoodStream"), None)
        assert dood is not None, data
        assert "/e/" in dood["embed_url"], dood
        from urllib.parse import urlparse
        assert urlparse(dood["embed_url"]).netloc.lower() == "dsvplay.com", dood

    def test_create_new_mirror_resolves_and_persists(self, admin_token, hosts):
        headers = {"Authorization": f"Bearer {admin_token}"}
        dood = next(x for x in hosts if x["name"] == "DoodStream")
        payload = {
            "title": "TEST_ResolveLive",
            "description": "resolve dsvplay->playmogo",
            "links": [
                {"host_id": dood["id"], "embed_url": "https://dsvplay.com/d/ysledj039kb4"},
            ],
        }
        r = requests.post(f"{API}/mirrors", json=payload, headers=headers)
        assert r.status_code == 200, r.text
        m = r.json()
        mid = m["id"]
        slug = m["slug"]
        try:
            # 1) URL normalization: /d/ -> /e/
            assert m["links"][0]["embed_url"] == "https://dsvplay.com/e/ysledj039kb4", m["links"]

            # 2) Trigger /embed -> should resolve live domain
            r = requests.get(f"{API}/embed/{slug}", timeout=30)
            assert r.status_code == 200, r.text
            data = r.json()
            embed_url = data["hosts"][0]["embed_url"]
            assert "/e/ysledj039kb4" in embed_url, embed_url
            from urllib.parse import urlparse as _up
            assert _up(embed_url).netloc.lower() == "dsvplay.com", embed_url

            # 3) Confirm resolved_url persisted on the doc (canonical dsvplay.com)
            r = requests.get(f"{API}/mirrors/{mid}",
                             headers=headers)
            assert r.status_code == 200, r.text
            doc = r.json()
            link = doc["links"][0]
            assert link.get("resolved_url"), f"resolved_url not persisted: {link}"
            assert _up(link["resolved_url"]).netloc.lower() == "dsvplay.com", link["resolved_url"]
        finally:
            requests.delete(f"{API}/mirrors/{mid}", headers=headers)

    def test_check_endpoint_stores_resolved_url(self, admin_token, hosts):
        headers = {"Authorization": f"Bearer {admin_token}"}
        dood = next(x for x in hosts if x["name"] == "DoodStream")
        payload = {
            "title": "TEST_CheckResolved",
            "description": "verify /check persists resolved_url",
            "links": [{"host_id": dood["id"], "embed_url": "https://dsvplay.com/e/ysledj039kb4"}],
        }
        r = requests.post(f"{API}/mirrors", json=payload, headers=headers)
        assert r.status_code == 200, r.text
        mid = r.json()["id"]
        try:
            r = requests.post(f"{API}/mirrors/{mid}/check", headers=headers, timeout=60)
            assert r.status_code == 200, r.text
            link = r.json()["links"][0]
            assert link.get("resolved_url"), f"resolved_url missing after /check: {link}"
            from urllib.parse import urlparse as _up
            assert _up(link["resolved_url"]).netloc.lower() == "dsvplay.com", link["resolved_url"]
            assert link["status"] == "online"
        finally:
            requests.delete(f"{API}/mirrors/{mid}", headers=headers)


# ---- Host API Integration (iteration 6) ----
class TestHostApiIntegration:
    """DoodStream + VOE live API integration (dsvplay/voe.sx bypass)."""

    def test_hosts_have_api_provider(self, hosts):
        dood = next(x for x in hosts if x["name"] == "DoodStream")
        voe = next(x for x in hosts if x["name"] == "VOE")
        assert dood.get("api_provider") == "doodstream", dood
        assert voe.get("api_provider") == "voe", voe

    def test_embed_smiooaxb_uses_api_domains(self):
        r = requests.get(f"{API}/embed/SMioOAxb", timeout=30)
        if r.status_code != 200:
            pytest.skip("Seed mirror SMioOAxb not present")
        data = r.json()
        by = {h["host_name"]: h for h in data["hosts"]}
        voe = by.get("VOE"); dood = by.get("DoodStream")
        assert voe and dood, data
        # VOE: online, /e/<code>, NOT voe.sx (rotating direct domain)
        assert voe["status"] == "online", voe
        assert "/e/" in voe["embed_url"], voe
        from urllib.parse import urlparse
        voe_host = urlparse(voe["embed_url"]).netloc.lower()
        assert voe_host and voe_host != "voe.sx", (
            f"VOE embed_url should be on rotating direct domain, got {voe_host}"
        )
        # DoodStream: online, /e/<code>, CANONICAL dsvplay.com (iteration 7)
        assert dood["status"] == "online", dood
        assert "/e/" in dood["embed_url"], dood
        dood_host = urlparse(dood["embed_url"]).netloc.lower()
        assert dood_host == "dsvplay.com", (
            f"DoodStream embed_url should be canonical dsvplay.com, got {dood_host}"
        )

    # iteration 8: thumbnails
    def test_embed_smiooaxb_returns_thumbnail(self):
        r = requests.get(f"{API}/embed/SMioOAxb", timeout=30)
        if r.status_code != 200:
            pytest.skip("Seed mirror SMioOAxb not present")
        data = r.json()
        assert "thumbnail" in data, "top-level thumbnail key missing"
        # top-level thumbnail should be set (comes from DoodStream splash_img)
        assert data["thumbnail"] and isinstance(data["thumbnail"], str), data.get("thumbnail")
        assert "doimg.net" in data["thumbnail"], data["thumbnail"]
        by = {h["host_name"]: h for h in data["hosts"]}
        dood = by.get("DoodStream")
        assert dood is not None
        assert dood.get("thumbnail"), "DoodStream host entry missing thumbnail"
        assert "doimg.net" in dood["thumbnail"]


    def test_manual_check_uses_api_populates_title(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{API}/mirrors", headers=headers)
        assert r.status_code == 200
        target = next((m for m in r.json() if m.get("slug") == "SMioOAxb"), None)
        if not target:
            pytest.skip("Seed mirror SMioOAxb not present")
        r = requests.post(f"{API}/mirrors/{target['id']}/check", headers=headers, timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        by_host_name = {}
        # need host lookup - fetch hosts
        hs = requests.get(f"{API}/hosts", headers=headers).json()
        host_by_id = {h["id"]: h["name"] for h in hs}
        from urllib.parse import urlparse
        for l in data["links"]:
            name = host_by_id.get(l["host_id"])
            assert l["status"] == "online", (name, l)
            assert l.get("resolved_url"), (name, l)
            resolved_host = urlparse(l["resolved_url"]).netloc.lower()
            if name == "VOE":
                assert resolved_host != "voe.sx", l
            if name == "DoodStream":
                assert resolved_host == "dsvplay.com", l
                # title from doodstream API
                assert l.get("title"), f"Doodstream title not populated: {l}"

    def test_create_flow_resolves_both_providers(self, admin_token, hosts):
        headers = {"Authorization": f"Bearer {admin_token}"}
        dood = next(x for x in hosts if x["name"] == "DoodStream")
        voe = next(x for x in hosts if x["name"] == "VOE")
        payload = {
            "title": "TEST_ApiResolveFlow",
            "description": "iter6 create flow",
            "links": [
                {"host_id": dood["id"], "embed_url": "https://dsvplay.com/d/9bvi9u4wu0j1"},
                {"host_id": voe["id"], "embed_url": "https://voe.sx/rjseg1wmsyv6"},
            ],
        }
        r = requests.post(f"{API}/mirrors", json=payload, headers=headers)
        assert r.status_code == 200, r.text
        mid = r.json()["id"]
        try:
            # background resolution ~6s
            time.sleep(8)
            r = requests.get(f"{API}/mirrors/{mid}", headers=headers)
            assert r.status_code == 200, r.text
            doc = r.json()
            from urllib.parse import urlparse
            host_by_id = {dood["id"]: "DoodStream", voe["id"]: "VOE"}
            for l in doc["links"]:
                name = host_by_id.get(l["host_id"])
                assert l["status"] == "online", (name, l)
                assert l.get("resolved_url"), (name, l)
                h = urlparse(l["resolved_url"]).netloc.lower()
                if name == "VOE":
                    assert h and h != "voe.sx", (name, l)
                if name == "DoodStream":
                    assert h == "dsvplay.com", (name, l)
        finally:
            requests.delete(f"{API}/mirrors/{mid}", headers=headers)


# ---- Site Settings ----
class TestSiteSettings:
    def test_get_settings_public_no_auth(self):
        r = requests.get(f"{API}/settings")
        assert r.status_code == 200
        d = r.json()
        for k in ["site_name", "tagline", "description", "footer_text"]:
            assert k in d
        assert isinstance(d["site_name"], str) and len(d["site_name"]) > 0

    def test_non_admin_cannot_update_settings(self, user_creds):
        r = requests.put(f"{API}/admin/settings",
                         json={"site_name": "Hack", "tagline": "x", "description": "y", "footer_text": "z"},
                         headers={"Authorization": f"Bearer {user_creds['token']}"})
        assert r.status_code == 403

    def test_admin_update_and_reset_settings(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        # snapshot current
        orig = requests.get(f"{API}/settings").json()
        try:
            new_name = f"TEST_Site_{uuid.uuid4().hex[:6]}"
            payload = {"site_name": new_name, "tagline": "TEST tagline",
                       "description": "TEST desc", "footer_text": "TEST footer"}
            r = requests.put(f"{API}/admin/settings", json=payload, headers=headers)
            assert r.status_code == 200
            assert r.json()["site_name"] == new_name
            # verify GET returns new value
            r = requests.get(f"{API}/settings")
            assert r.status_code == 200
            assert r.json()["site_name"] == new_name
            assert r.json()["tagline"] == "TEST tagline"
        finally:
            # reset to original defaults from problem statement
            reset_payload = {
                "site_name": orig.get("site_name", "MirrorStream"),
                "tagline": orig.get("tagline", "One embed link. Every host. Maximum revenue."),
                "description": orig.get("description", ""),
                "footer_text": orig.get("footer_text", "For legal content only."),
            }
            # if the original was our test value (unlikely but safe), force defaults
            if reset_payload["site_name"].startswith("TEST_"):
                reset_payload = {
                    "site_name": "MirrorStream",
                    "tagline": "One embed link. Every host. Maximum revenue.",
                    "description": "Paste your embed links from Doodstream, VOE and other hosters. We generate a single player that always shows your viewers the best-paying source for their country.",
                    "footer_text": "For legal content only.",
                }
            requests.put(f"{API}/admin/settings", json=reset_payload, headers=headers)

# ---- Ad Settings (iteration 9) ----
class TestAdSettings:
    def test_get_settings_has_ad_keys_default_empty(self):
        r = requests.get(f"{API}/settings")
        assert r.status_code == 200
        d = r.json()
        for k in ["ad_header", "ad_footer", "ad_player_top", "ad_player_bottom"]:
            assert k in d, f"missing {k}"
        # after previous iteration cleanup they should be empty; but if not empty
        # we still just verify string type
        for k in ["ad_header", "ad_footer", "ad_player_top", "ad_player_bottom"]:
            assert isinstance(d[k], str)

    def test_admin_update_and_reset_ads(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        orig = requests.get(f"{API}/settings").json()
        try:
            payload = {
                "site_name": orig.get("site_name", "MirrorStream"),
                "tagline": orig.get("tagline", ""),
                "description": orig.get("description", ""),
                "footer_text": orig.get("footer_text", ""),
                "ad_header": '<div data-testid="live-ad-header">MY AD</div>',
                "ad_footer": '<div data-testid="live-ad-footer">FOOT</div>',
                "ad_player_top": '<div data-testid="live-ad-player-top">PT</div>',
                "ad_player_bottom": '<div data-testid="live-ad-player-bottom">PB</div>',
            }
            r = requests.put(f"{API}/admin/settings", json=payload, headers=headers)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["ad_header"] == payload["ad_header"]
            # verify GET
            r = requests.get(f"{API}/settings")
            d = r.json()
            for k in ("ad_header", "ad_footer", "ad_player_top", "ad_player_bottom"):
                assert d[k] == payload[k], f"{k} not persisted: {d[k]}"
        finally:
            # reset ads to empty, preserve base settings
            reset = {
                "site_name": "MirrorStream",
                "tagline": "One embed link. Every host. Maximum revenue.",
                "description": orig.get("description", ""),
                "footer_text": "For legal content only.",
                "ad_header": "",
                "ad_footer": "",
                "ad_player_top": "",
                "ad_player_bottom": "",
            }
            requests.put(f"{API}/admin/settings", json=reset, headers=headers)
            # confirm reset
            d = requests.get(f"{API}/settings").json()
            for k in ("ad_header", "ad_footer", "ad_player_top", "ad_player_bottom"):
                assert d[k] == "", f"ad {k} not reset: {d[k]!r}"




# ---- API-key masking + FireStream integration (iteration 10) ----
class TestFireStreamAndHostKeys:
    """Host keys stay private and FireStream links resolve through its official API."""

    @staticmethod
    def _headers(token):
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _host_payload(host, api_key_marker=False):
        payload = {
            "name": host["name"],
            "domain": host["domain"],
            "default_rate": host["default_rate"],
            "tiers": host.get("tiers", []),
            "is_active": host.get("is_active", True),
            "api_provider": host.get("api_provider"),
        }
        if api_key_marker is not False:
            payload["api_key"] = api_key_marker
        return payload

    def test_admin_login_returns_access_token(self):
        response = requests.post(
            f"{API}/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert isinstance(data.get("access_token"), str) and data["access_token"]
        assert data["user"]["email"] == ADMIN_EMAIL
        assert data["user"]["role"] == "admin"

    def test_authenticated_user_gets_only_masked_host_keys(self, user_creds):
        response = requests.get(
            f"{API}/hosts",
            headers=self._headers(user_creds["token"]),
        )
        assert response.status_code == 200, response.text
        hosts_data = response.json()
        assert isinstance(hosts_data, list) and hosts_data
        for host in hosts_data:
            assert "api_key" not in host, f"Raw API key field leaked for {host.get('name')}"
            assert isinstance(host.get("has_api_key"), bool), host
        by_provider = {host.get("api_provider"): host for host in hosts_data}
        for provider in ("doodstream", "voe", "firestream"):
            assert provider in by_provider, f"Seeded provider missing: {provider}"
            assert by_provider[provider]["has_api_key"] is True, provider

    def test_existing_firestream_key_survives_omitted_and_empty_updates(self, admin_token):
        headers = self._headers(admin_token)
        hosts_response = requests.get(f"{API}/hosts", headers=headers)
        assert hosts_response.status_code == 200, hosts_response.text
        firestream = next(
            host for host in hosts_response.json()
            if host.get("api_provider") == "firestream"
        )
        assert firestream["has_api_key"] is True

        omitted_payload = self._host_payload(firestream)
        response = requests.put(
            f"{API}/hosts/{firestream['id']}", json=omitted_payload, headers=headers
        )
        assert response.status_code == 200, response.text
        assert response.json()["has_api_key"] is True
        assert "api_key" not in response.json()

        empty_payload = self._host_payload(firestream, "")
        response = requests.put(
            f"{API}/hosts/{firestream['id']}", json=empty_payload, headers=headers
        )
        assert response.status_code == 200, response.text
        assert response.json()["has_api_key"] is True
        assert "api_key" not in response.json()

    def test_create_and_replace_new_host_key_without_leak(self, admin_token):
        headers = self._headers(admin_token)
        unique = uuid.uuid4().hex[:10]
        payload = {
            "name": f"TEST_FireHost_{unique}",
            "domain": f"test-{unique}.example",
            "default_rate": 2.5,
            "tiers": [],
            "is_active": True,
            "api_provider": "firestream",
            "api_key": f"TEST_INITIAL_{unique}",
        }
        response = requests.post(f"{API}/hosts", json=payload, headers=headers)
        assert response.status_code == 200, response.text
        created = response.json()
        host_id = created["id"]
        try:
            assert created["name"] == payload["name"]
            assert created["api_provider"] == "firestream"
            assert created["has_api_key"] is True
            assert "api_key" not in created

            replacement = self._host_payload(created, f"TEST_REPLACEMENT_{unique}")
            response = requests.put(
                f"{API}/hosts/{host_id}", json=replacement, headers=headers
            )
            assert response.status_code == 200, response.text
            assert response.json()["has_api_key"] is True
            assert "api_key" not in response.json()

            listed = requests.get(f"{API}/hosts", headers=headers)
            assert listed.status_code == 200
            persisted = next(host for host in listed.json() if host["id"] == host_id)
            assert persisted["name"] == payload["name"]
            assert persisted["has_api_key"] is True
            assert "api_key" not in persisted
        finally:
            delete_response = requests.delete(f"{API}/hosts/{host_id}", headers=headers)
            assert delete_response.status_code == 200

    @pytest.mark.parametrize(
        ("embed_url", "expected_status", "expected_title"),
        [
            ("https://firestream.to/e/1uuFmyaj", "online", "API Upload Test"),
            ("https://firestream.to/e/zzzzznope", "offline", None),
        ],
    )
    def test_firestream_link_resolution(
        self, admin_token, embed_url, expected_status, expected_title
    ):
        headers = self._headers(admin_token)
        hosts_response = requests.get(f"{API}/hosts", headers=headers)
        assert hosts_response.status_code == 200, hosts_response.text
        firestream = next(
            host for host in hosts_response.json()
            if host.get("api_provider") == "firestream"
        )
        create_response = requests.post(
            f"{API}/mirrors",
            json={
                "title": f"TEST_FireStream_{uuid.uuid4().hex[:8]}",
                "description": "FireStream API resolution test",
                "links": [{"host_id": firestream["id"], "embed_url": embed_url}],
            },
            headers=headers,
        )
        assert create_response.status_code == 200, create_response.text
        mirror = create_response.json()
        mirror_id = mirror["id"]
        try:
            resolved = None
            for _ in range(10):
                time.sleep(2)
                get_response = requests.get(
                    f"{API}/mirrors/{mirror_id}", headers=headers
                )
                assert get_response.status_code == 200, get_response.text
                resolved = get_response.json()
                if resolved["links"][0]["status"] != "pending":
                    break
            link = resolved["links"][0]
            assert link["status"] == expected_status, link
            assert link["resolved_url"].endswith(embed_url.rsplit("/", 1)[-1])
            assert link["last_checked"]
            if expected_title:
                assert link.get("title") == expected_title, link
        finally:
            delete_response = requests.delete(
                f"{API}/mirrors/{mirror_id}", headers=headers
            )
            assert delete_response.status_code == 200
            confirm = requests.get(f"{API}/mirrors/{mirror_id}", headers=headers)
            assert confirm.status_code == 404
