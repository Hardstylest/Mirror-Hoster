"""MirrorStream backend API tests."""
import hashlib
import io
import json
import os
import re
import uuid
import time
import zipfile
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
    creds = {"email": email, "password": password, "token": data["access_token"], "id": data["user"]["id"]}
    yield creds
    admin_login = requests.post(
        f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if admin_login.status_code == 200:
        requests.delete(
            f"{API}/admin/users/{creds['id']}",
            headers={"Authorization": f"Bearer {admin_login.json()['access_token']}"},
        )


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

    def test_embed_public_no_auth_sorting_ES(self, hosts):
        r = requests.get(f"{API}/embed/{pytest.mirror_slug}?country=ES")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["country_code"] == "ES"
        embedded_hosts = data["hosts"]
        assert len(embedded_hosts) == 2
        configured = {host["name"]: host for host in hosts}
        expected_rates = {}
        for name in ("VOE", "DoodStream"):
            host = configured[name]
            expected_rates[name] = next(
                (float(tier["rate"]) for tier in host["tiers"] if "ES" in tier["countries"]),
                float(host["default_rate"]),
            )
        expected_order = sorted(expected_rates, key=expected_rates.get, reverse=True)
        assert [host["host_name"] for host in embedded_hosts] == expected_order
        for host in embedded_hosts:
            assert host["rate"] == expected_rates[host["host_name"]]

    def test_embed_public_no_auth_sorting_US(self, hosts):
        r = requests.get(f"{API}/embed/{pytest.mirror_slug}?country=US")
        assert r.status_code == 200
        data = r.json()
        embedded_hosts = data["hosts"]
        configured = {host["name"]: host for host in hosts}
        expected_rates = {}
        for name in ("VOE", "DoodStream"):
            host = configured[name]
            expected_rates[name] = next(
                (float(tier["rate"]) for tier in host["tiers"] if "US" in tier["countries"]),
                float(host["default_rate"]),
            )
        expected_order = sorted(expected_rates, key=expected_rates.get, reverse=True)
        assert [host["host_name"] for host in embedded_hosts] == expected_order
        for host in embedded_hosts:
            assert host["rate"] == expected_rates[host["host_name"]]

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



# ---- Tier auto-update + offline-link auto-fix (iteration 11) ----
class TestTierRefreshAndAutoFix:
    """On-demand tier scraping and provider-specific offline-link replacement flows."""

    @staticmethod
    def _headers(token):
        return {"Authorization": f"Bearer {token}"}

    def test_refresh_tiers_updates_voe_and_firestream(self, admin_token):
        headers = self._headers(admin_token)
        before_response = requests.get(f"{API}/hosts", headers=headers)
        assert before_response.status_code == 200, before_response.text
        before = {host["id"]: host for host in before_response.json()}

        response = requests.post(
            f"{API}/admin/hosts/refresh-tiers", json={}, headers=headers, timeout=90
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert isinstance(data.get("results"), list), data
        results = {before[item["host_id"]]["api_provider"]: item for item in data["results"]}
        for provider in ("voe", "firestream"):
            assert results[provider]["ok"] is True, results[provider]
            assert isinstance(results[provider]["count"], int) and results[provider]["count"] > 0

        hosts_response = requests.get(f"{API}/hosts", headers=headers)
        assert hosts_response.status_code == 200, hosts_response.text
        by_provider = {host.get("api_provider"): host for host in hosts_response.json()}
        voe_tier_one = by_provider["voe"]["tiers"][0]
        fire_tier_one = by_provider["firestream"]["tiers"][0]
        assert voe_tier_one["rate"] == 45.0, voe_tier_one
        assert set(voe_tier_one["countries"]) == {"AU", "GB", "US"}, voe_tier_one
        assert fire_tier_one["rate"] == 40.0, fire_tier_one
        assert set(fire_tier_one["countries"]) == {"AU", "DE", "US", "GB"}, fire_tier_one
        for provider in ("voe", "firestream"):
            stamp = by_provider[provider].get("tiers_updated_at")
            assert isinstance(stamp, str) and stamp, by_provider[provider]

    def test_doodstream_autofix_replaces_and_persists_online_link(self, admin_token):
        headers = self._headers(admin_token)
        hosts_response = requests.get(f"{API}/hosts", headers=headers)
        dood = next(h for h in hosts_response.json() if h.get("api_provider") == "doodstream")
        create_response = requests.post(
            f"{API}/mirrors",
            json={
                "title": "Pranksters 3 (2019)",
                "description": "TEST_AutoFix_DoodStream",
                "links": [{
                    "host_id": dood["id"],
                    "embed_url": "https://doodstream.com/e/deadcodeXYZ",
                }],
            },
            headers=headers,
        )
        assert create_response.status_code == 200, create_response.text
        mirror_id = create_response.json()["id"]
        try:
            time.sleep(4)
            response = requests.post(
                f"{API}/mirrors/{mirror_id}/autofix/{dood['id']}",
                headers=headers,
                timeout=45,
            )
            assert response.status_code == 200, response.text
            result = response.json()
            assert result["ok"] is True, result
            assert result["new_url"].startswith("https://doodstream.com/e/"), result
            assert result["new_url"] != "https://doodstream.com/e/deadcodeXYZ"

            get_response = requests.get(f"{API}/mirrors/{mirror_id}", headers=headers)
            assert get_response.status_code == 200, get_response.text
            link = get_response.json()["links"][0]
            assert link["status"] == "online", link
            assert link["embed_url"] == result["new_url"], link
            assert link["embed_url"] != "https://doodstream.com/e/deadcodeXYZ"
        finally:
            delete_response = requests.delete(f"{API}/mirrors/{mirror_id}", headers=headers)
            assert delete_response.status_code == 200, delete_response.text
            assert requests.get(f"{API}/mirrors/{mirror_id}", headers=headers).status_code == 404

    def test_firestream_autofix_is_rejected(self, admin_token):
        headers = self._headers(admin_token)
        hosts_response = requests.get(f"{API}/hosts", headers=headers)
        firestream = next(h for h in hosts_response.json() if h.get("api_provider") == "firestream")
        create_response = requests.post(
            f"{API}/mirrors",
            json={
                "title": "TEST_AutoFix_Unsupported",
                "description": "TEST_AutoFix_FireStream",
                "links": [{
                    "host_id": firestream["id"],
                    "embed_url": "https://firestream.to/e/zzzzznope",
                }],
            },
            headers=headers,
        )
        assert create_response.status_code == 200, create_response.text
        mirror_id = create_response.json()["id"]
        try:
            response = requests.post(
                f"{API}/mirrors/{mirror_id}/autofix/{firestream['id']}", headers=headers
            )
            assert response.status_code == 400, response.text
            assert response.json()["detail"] == "FireStream login not configured"
        finally:
            delete_response = requests.delete(f"{API}/mirrors/{mirror_id}", headers=headers)
            assert delete_response.status_code == 200, delete_response.text

    def test_non_owner_cannot_autofix_another_users_mirror(
        self, admin_token, user_creds
    ):
        admin_headers = self._headers(admin_token)
        user_headers = self._headers(user_creds["token"])
        hosts_response = requests.get(f"{API}/hosts", headers=admin_headers)
        dood = next(h for h in hosts_response.json() if h.get("api_provider") == "doodstream")
        create_response = requests.post(
            f"{API}/mirrors",
            json={
                "title": "Pranksters 3 (2019)",
                "description": "TEST_AutoFix_Owner_Guard",
                "links": [{
                    "host_id": dood["id"],
                    "embed_url": "https://doodstream.com/e/deadcodeXYZ",
                }],
            },
            headers=admin_headers,
        )
        assert create_response.status_code == 200, create_response.text
        mirror_id = create_response.json()["id"]
        try:
            response = requests.post(
                f"{API}/mirrors/{mirror_id}/autofix/{dood['id']}", headers=user_headers
            )
            assert response.status_code == 403, response.text
            assert response.json()["detail"] == "Not allowed"
        finally:
            delete_response = requests.delete(
                f"{API}/mirrors/{mirror_id}", headers=admin_headers
            )
            assert delete_response.status_code == 200, delete_response.text


# ---- Admin user management + fix history (iteration 12) ----
class TestAdminUserManagementAndFixLogs:
    """Create/reset/search-support APIs, role/delete regression, and fix-log visibility."""

    @staticmethod
    def _headers(token):
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _create_admin_managed_user(admin_token, role="user"):
        unique = uuid.uuid4().hex[:10]
        payload = {
            "name": f"TEST_AdminManaged_{unique}",
            "email": f"TEST_admin_managed_{unique}@example.com",
            "password": "OldPass@123",
            "role": role,
        }
        response = requests.post(
            f"{API}/admin/users",
            json=payload,
            headers=TestAdminUserManagementAndFixLogs._headers(admin_token),
        )
        assert response.status_code in (200, 201), response.text
        return payload, response.json()

    @staticmethod
    def _delete_user(admin_token, user_id):
        response = requests.delete(
            f"{API}/admin/users/{user_id}",
            headers=TestAdminUserManagementAndFixLogs._headers(admin_token),
        )
        assert response.status_code in (200, 404), response.text

    def test_admin_create_admin_user_login_duplicate_and_no_hash(self, admin_token):
        payload, created = self._create_admin_managed_user(admin_token, role="admin")
        user_id = created["id"]
        try:
            assert created["name"] == payload["name"]
            assert created["email"] == payload["email"].lower()
            assert created["role"] == "admin"
            assert isinstance(user_id, str) and user_id
            assert "password" not in created and "password_hash" not in created

            login = requests.post(
                f"{API}/auth/login",
                json={"email": payload["email"], "password": payload["password"]},
            )
            assert login.status_code == 200, login.text
            assert login.json()["user"]["role"] == "admin"
            assert login.json()["user"]["id"] == user_id

            duplicate = requests.post(
                f"{API}/admin/users",
                json=payload,
                headers=self._headers(admin_token),
            )
            assert duplicate.status_code == 400, duplicate.text
            assert duplicate.json()["detail"] == "Email already registered"

            listed = requests.get(
                f"{API}/admin/users", headers=self._headers(admin_token)
            )
            persisted = next(user for user in listed.json() if user["id"] == user_id)
            assert persisted["email"] == payload["email"].lower()
            assert persisted["role"] == "admin"
            assert "password_hash" not in persisted
        finally:
            self._delete_user(admin_token, user_id)

    def test_non_admin_cannot_create_user(self, user_creds):
        response = requests.post(
            f"{API}/admin/users",
            json={
                "name": "TEST_Forbidden",
                "email": f"TEST_forbidden_{uuid.uuid4().hex[:8]}@example.com",
                "password": "TestPass@123",
                "role": "user",
            },
            headers=self._headers(user_creds["token"]),
        )
        assert response.status_code == 403, response.text
        assert response.json()["detail"] == "Admin access required"

    def test_admin_password_reset_new_works_old_fails_and_short_rejected(self, admin_token):
        payload, created = self._create_admin_managed_user(admin_token)
        user_id = created["id"]
        new_password = "NewPass@456"
        try:
            reset = requests.put(
                f"{API}/admin/users/{user_id}/password",
                json={"password": new_password},
                headers=self._headers(admin_token),
            )
            assert reset.status_code == 200, reset.text
            assert reset.json() == {"ok": True}

            old_login = requests.post(
                f"{API}/auth/login",
                json={"email": payload["email"], "password": payload["password"]},
            )
            assert old_login.status_code == 401, old_login.text
            assert old_login.json()["detail"] == "Invalid email or password"

            new_login = requests.post(
                f"{API}/auth/login",
                json={"email": payload["email"], "password": new_password},
            )
            assert new_login.status_code == 200, new_login.text
            assert new_login.json()["user"]["id"] == user_id

            short = requests.put(
                f"{API}/admin/users/{user_id}/password",
                json={"password": "12345"},
                headers=self._headers(admin_token),
            )
            assert short.status_code == 422, short.text
            detail = short.json()["detail"]
            assert isinstance(detail, list) and detail[0]["type"] == "string_too_short"
        finally:
            self._delete_user(admin_token, user_id)

    def test_role_toggle_delete_and_self_protection_regression(self, admin_token):
        headers = self._headers(admin_token)
        me = requests.get(f"{API}/auth/me", headers=headers)
        assert me.status_code == 200
        self_id = me.json()["id"]

        self_role = requests.put(
            f"{API}/admin/users/{self_id}/role",
            json={"role": "user"},
            headers=headers,
        )
        assert self_role.status_code == 400, self_role.text
        assert self_role.json()["detail"] == "You cannot change your own role"
        self_delete = requests.delete(f"{API}/admin/users/{self_id}", headers=headers)
        assert self_delete.status_code == 400, self_delete.text
        assert self_delete.json()["detail"] == "You cannot delete your own account"

        payload, created = self._create_admin_managed_user(admin_token)
        user_id = created["id"]
        try:
            promote = requests.put(
                f"{API}/admin/users/{user_id}/role",
                json={"role": "admin"},
                headers=headers,
            )
            assert promote.status_code == 200, promote.text
            assert promote.json() == {"ok": True, "role": "admin"}
            listed = requests.get(f"{API}/admin/users", headers=headers).json()
            assert next(u for u in listed if u["id"] == user_id)["role"] == "admin"

            demote = requests.put(
                f"{API}/admin/users/{user_id}/role",
                json={"role": "user"},
                headers=headers,
            )
            assert demote.status_code == 200, demote.text
            assert demote.json()["role"] == "user"

            deleted = requests.delete(f"{API}/admin/users/{user_id}", headers=headers)
            assert deleted.status_code == 200, deleted.text
            assert deleted.json() == {"ok": True}
            users_after = requests.get(f"{API}/admin/users", headers=headers).json()
            assert all(user["id"] != user_id for user in users_after)
            user_id = None
        finally:
            if user_id:
                self._delete_user(admin_token, user_id)

    def test_fix_logs_admin_shape_order_and_normal_user_scope(self, admin_token, user_creds):
        admin_response = requests.get(
            f"{API}/fix-logs", headers=self._headers(admin_token)
        )
        assert admin_response.status_code == 200, admin_response.text
        logs = admin_response.json()
        assert isinstance(logs, list)
        timestamps = [entry["created_at"] for entry in logs]
        assert timestamps == sorted(timestamps, reverse=True)
        for entry in logs:
            assert isinstance(entry.get("id"), str) and entry["id"]
            for field in ("mirror_title", "host_name", "new_url", "created_at"):
                assert isinstance(entry.get(field), str) and entry[field], (field, entry)
            assert "_id" not in entry

        user_response = requests.get(
            f"{API}/fix-logs", headers=self._headers(user_creds["token"])
        )
        assert user_response.status_code == 200, user_response.text
        assert user_response.json() == []


# ---- Authentication playbook checks (iteration 12) ----
class TestAuthenticationPlaybook:
    """Cookie, bcrypt-storage, CORS behavior, and brute-force controls."""

    def test_login_sets_httponly_cookie(self):
        response = requests.post(
            f"{API}/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert response.status_code == 200, response.text
        cookie_header = response.headers.get("set-cookie", "")
        assert "access_token=" in cookie_header
        assert "httponly" in cookie_header.lower()
        assert response.cookies.get("access_token") == response.json()["access_token"]

    def test_new_password_hash_is_bcrypt_2b_and_not_exposed(self, admin_token):
        from dotenv import dotenv_values
        from pymongo import MongoClient

        payload, created = TestAdminUserManagementAndFixLogs._create_admin_managed_user(admin_token)
        user_id = created["id"]
        try:
            env = dotenv_values("/app/backend/.env")
            mongo = MongoClient(env["MONGO_URL"], serverSelectionTimeoutMS=5000)
            stored = mongo[env["DB_NAME"]].users.find_one({"email": payload["email"].lower()})
            assert stored is not None
            assert stored["password_hash"].startswith("$2b$")
            assert payload["password"] not in stored["password_hash"]
            assert "password_hash" not in created
            mongo.close()
        finally:
            TestAdminUserManagementAndFixLogs._delete_user(admin_token, user_id)

    def test_brute_force_lockout_after_five_failures(self):
        email = f"TEST_lockout_{uuid.uuid4().hex[:10]}@example.com"
        statuses = []
        for _ in range(6):
            response = requests.post(
                f"{API}/auth/login", json={"email": email, "password": "wrongpass"}
            )
            statuses.append(response.status_code)
        assert statuses[:5] == [401] * 5, statuses
        assert statuses[5] == 429, statuses

    def test_cors_preflight_supports_credentialed_origin(self):
        origin = "https://qa.example.test"
        response = requests.options(
            f"{API}/auth/login",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert response.status_code in (200, 204), response.text
        assert response.headers.get("access-control-allow-credentials") == "true"
        assert response.headers.get("access-control-allow-origin") == origin



# ---- New hosters, security settings, and login warnings (iteration 13) ----
class TestNewHostersAndSecurity:
    """Seeded provider metadata, key validation, settings privacy, and alert lifecycle."""

    @staticmethod
    def _headers(token):
        return {"Authorization": f"Bearer {token}"}

    def test_all_eight_seeded_hosters_and_tiers(self, admin_token):
        response = requests.get(f"{API}/hosts", headers=self._headers(admin_token))
        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data) == 8, f"Expected exactly 8 seeded hosters, got {len(data)}"
        by_provider = {host.get("api_provider"): host for host in data}
        expected = {
            "doodstream": "DoodStream",
            "voe": "VOE",
            "firestream": "FireStream",
            "playmate": "Playmate",
            "vidara": "Vidara",
            "streamtape": "Streamtape",
            "vinovo": "Vinovo",
            "vidnest": "VidNest",
        }
        for provider, name in expected.items():
            assert provider in by_provider, f"Missing provider {provider}: {by_provider.keys()}"
            host = by_provider[provider]
            assert host["name"] == name
            assert "api_key" not in host and "login_password" not in host
            assert isinstance(host.get("has_api_key"), bool)
            assert isinstance(host.get("tiers"), list)
            if provider == "streamtape":
                assert host["tiers"] == []
            else:
                assert len(host["tiers"]) > 0, f"{name} should have earning tiers"

    @pytest.mark.parametrize(
        "provider", ["playmate", "vidara", "streamtape", "vinovo", "vidnest"]
    )
    def test_new_hoster_missing_key_is_graceful_and_secret_free(self, admin_token, provider):
        response = requests.post(
            f"{API}/hosts/test-key",
            json={"api_provider": provider, "api_key": None, "login_email": None},
            headers=self._headers(admin_token),
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data == {"ok": False, "message": "No API key set"}
        assert "api_key" not in data and "secret" not in data

    def test_settings_antiadblock_roundtrip_and_turnstile_secret_never_leaks(self, admin_token):
        headers = self._headers(admin_token)
        original_response = requests.get(f"{API}/settings")
        assert original_response.status_code == 200, original_response.text
        original = original_response.json()
        assert "turnstile_secret_key" not in original
        assert isinstance(original.get("has_turnstile_secret"), bool)

        payload = {
            key: original.get(key, default)
            for key, default in {
                "site_name": "MirrorStream", "tagline": "", "description": "", "footer_text": "",
                "ad_header": "", "ad_footer": "", "ad_player_top": "", "ad_player_bottom": "",
                "turnstile_enabled": False, "turnstile_site_key": "", "turnstile_secret_key": "",
                "turnstile_login": True, "turnstile_register": True, "turnstile_gate": True,
                "antiadblock_enabled": False,
            }.items()
        }
        try:
            payload["turnstile_enabled"] = False
            payload["antiadblock_enabled"] = True
            update = requests.put(f"{API}/admin/settings", json=payload, headers=headers)
            assert update.status_code == 200, update.text
            updated = update.json()
            assert updated["antiadblock_enabled"] is True
            assert "turnstile_secret_key" not in updated

            public = requests.get(f"{API}/settings")
            assert public.status_code == 200, public.text
            settings = public.json()
            assert settings["antiadblock_enabled"] is True
            assert settings["turnstile_enabled"] is False
            assert "turnstile_secret_key" not in settings
            assert isinstance(settings["has_turnstile_secret"], bool)
        finally:
            payload["antiadblock_enabled"] = False
            payload["turnstile_enabled"] = False
            restored = requests.put(f"{API}/admin/settings", json=payload, headers=headers)
            assert restored.status_code == 200, restored.text
            final = requests.get(f"{API}/settings").json()
            assert final["antiadblock_enabled"] is False
            assert final["turnstile_enabled"] is False
            assert "turnstile_secret_key" not in final

    def test_login_alert_created_listed_and_cleared(self, admin_token):
        headers = self._headers(admin_token)
        before_response = requests.get(f"{API}/admin/login-alerts", headers=headers)
        assert before_response.status_code == 200, before_response.text
        before_counts = {item["ip"]: item["count"] for item in before_response.json()}
        bad_email = f"TEST_alert_{uuid.uuid4().hex[:10]}@example.com"
        for _ in range(3):
            failed = requests.post(
                f"{API}/auth/login",
                json={"email": bad_email, "password": "wrongpass"},
            )
            assert failed.status_code == 401, failed.text
            assert failed.json()["detail"] == "Invalid email or password"

        listed = requests.get(f"{API}/admin/login-alerts", headers=headers)
        assert listed.status_code == 200, listed.text
        alerts = listed.json()
        alert = next(
            (
                item for item in alerts
                if item["kind"] == "login"
                and item["count"] >= before_counts.get(item["ip"], 0) + 3
            ),
            None,
        )
        assert alert is not None, {"before": before_counts, "after": alerts}
        assert alert["count"] >= 3
        assert isinstance(alert["locked"], bool)
        observed_ip = alert["ip"]

        cleared = requests.delete(
            f"{API}/admin/login-alerts/{observed_ip}", headers=headers
        )
        assert cleared.status_code == 200, cleared.text
        assert cleared.json() == {"ok": True}
        after = requests.get(f"{API}/admin/login-alerts", headers=headers)
        assert after.status_code == 200, after.text
        assert all(item["ip"] != observed_ip for item in after.json())

    def test_login_alerts_require_admin(self, user_creds):
        headers = self._headers(user_creds["token"])
        response = requests.get(f"{API}/admin/login-alerts", headers=headers)
        assert response.status_code == 403, response.text
        assert response.json()["detail"] == "Admin access required"



# ---- Iteration 14 targeted fix verification ----
class TestIteration14Fixes:
    """Autofix reachability, alert thresholds, secret redaction, and core regressions."""

    @staticmethod
    def _headers(token):
        return {"Authorization": f"Bearer {token}"}

    @pytest.mark.parametrize(
        ("provider", "expected_status"),
        [
            ("playmate", 200),
            ("vidara", 200),
            ("streamtape", 400),
            ("vinovo", 200),
            ("vidnest", 200),
        ],
    )
    def test_new_provider_autofix_is_reachable(self, admin_token, provider, expected_status):
        headers = self._headers(admin_token)
        hosts_response = requests.get(f"{API}/hosts", headers=headers)
        assert hosts_response.status_code == 200, hosts_response.text
        host = next(h for h in hosts_response.json() if h.get("api_provider") == provider)
        assert host["has_api_key"] is False, host

        created = requests.post(
            f"{API}/mirrors",
            json={
                "title": f"TEST_AutofixReachability_{provider}_{uuid.uuid4().hex[:8]}",
                "description": "Iteration 14 targeted autofix allowlist test",
                "links": [{
                    "host_id": host["id"],
                    "embed_url": f"https://{host['domain']}/e/TEST_missing_file",
                }],
            },
            headers=headers,
        )
        assert created.status_code == 200, created.text
        mirror = created.json()
        mirror_id = mirror["id"]
        try:
            response = requests.post(
                f"{API}/mirrors/{mirror_id}/autofix/{host['id']}",
                headers=headers,
                timeout=30,
            )
            assert response.status_code == expected_status, response.text
            data = response.json()
            assert data.get("detail") != "Auto-fix is not supported for this host", data
            if provider == "streamtape":
                assert data == {"detail": "Streamtape API-Login not configured"}
            else:
                assert data == {
                    "ok": False,
                    "message": "No matching online file found in your account",
                }
        finally:
            deleted = requests.delete(f"{API}/mirrors/{mirror_id}", headers=headers)
            assert deleted.status_code == 200, deleted.text
            assert requests.get(f"{API}/mirrors/{mirror_id}", headers=headers).status_code == 404

    def test_four_failed_logins_alert_is_not_locked_and_can_be_cleared(self, admin_token):
        headers = self._headers(admin_token)
        before_response = requests.get(f"{API}/admin/login-alerts", headers=headers)
        assert before_response.status_code == 200, before_response.text
        before = {
            (item["kind"], item["ip"]): item["count"]
            for item in before_response.json()
        }
        bad_email = f"TEST_iter14_alert_{uuid.uuid4().hex[:12]}@example.com"
        observed_ip = None
        try:
            for _ in range(4):
                failed = requests.post(
                    f"{API}/auth/login",
                    json={"email": bad_email, "password": "wrongpass"},
                )
                assert failed.status_code == 401, failed.text
                assert failed.json()["detail"] == "Invalid email or password"

            listed = requests.get(f"{API}/admin/login-alerts", headers=headers)
            assert listed.status_code == 200, listed.text
            candidates = [
                item for item in listed.json()
                if item["kind"] == "login"
                and item["count"] >= before.get(("login", item["ip"]), 0) + 4
            ]
            assert candidates, {"before": before, "after": listed.json()}
            alert = max(candidates, key=lambda item: item["count"])
            observed_ip = alert["ip"]
            assert alert["count"] >= 4
            assert alert["locked"] is False, alert
        finally:
            if observed_ip:
                cleared = requests.delete(
                    f"{API}/admin/login-alerts/{observed_ip}", headers=headers
                )
                assert cleared.status_code == 200, cleared.text
                after = requests.get(f"{API}/admin/login-alerts", headers=headers)
                assert after.status_code == 200, after.text
                assert all(item["ip"] != observed_ip for item in after.json())

    def test_settings_and_key_test_never_leak_secrets(self, admin_token):
        settings_response = requests.get(f"{API}/settings")
        assert settings_response.status_code == 200, settings_response.text
        settings = settings_response.json()
        assert "turnstile_secret_key" not in settings
        assert isinstance(settings.get("has_turnstile_secret"), bool)

        marker = f"TEST_SECRET_MUST_NOT_LEAK_{uuid.uuid4().hex}"
        key_response = requests.post(
            f"{API}/hosts/test-key",
            json={"api_provider": "vidnest", "api_key": marker},
            headers=self._headers(admin_token),
            timeout=30,
        )
        assert key_response.status_code == 200, key_response.text
        data = key_response.json()
        assert data.get("ok") is False, data
        assert marker not in key_response.text
        assert "api_key" not in data and "secret" not in data

    def test_new_hosters_and_public_embed_regression(self, admin_token):
        headers = self._headers(admin_token)
        hosts_response = requests.get(f"{API}/hosts", headers=headers)
        assert hosts_response.status_code == 200, hosts_response.text
        by_provider = {host.get("api_provider"): host for host in hosts_response.json()}
        for provider in ("playmate", "vidara", "streamtape", "vinovo", "vidnest"):
            assert provider in by_provider, by_provider.keys()

        playmate = by_provider["playmate"]
        created = requests.post(
            f"{API}/mirrors",
            json={
                "title": f"TEST_PublicEmbed_{uuid.uuid4().hex[:8]}",
                "description": "Iteration 14 public player regression",
                "links": [{
                    "host_id": playmate["id"],
                    "embed_url": "https://playmate.to/e/TEST_public_player",
                }],
            },
            headers=headers,
        )
        assert created.status_code == 200, created.text
        mirror = created.json()
        try:
            embed_api = requests.get(f"{API}/embed/{mirror['slug']}?country=DE", timeout=30)
            assert embed_api.status_code == 200, embed_api.text
            data = embed_api.json()
            assert data["slug"] == mirror["slug"]
            assert data["title"] == mirror["title"]
            assert len(data["hosts"]) == 1
            assert data["hosts"][0]["host_name"] == "Playmate"

            player_page = requests.get(f"{BASE_URL}/e/{mirror['slug']}", timeout=30)
            assert player_page.status_code == 200, player_page.text
            assert "root" in player_page.text
        finally:
            deleted = requests.delete(f"{API}/mirrors/{mirror['id']}", headers=headers)
            assert deleted.status_code == 200, deleted.text


# ---- Backup server-file fix and safe restore verification (iteration 17) ----
class TestBackupServerFilesAndRestore:
    """Backup ZIP contents, settings privacy, and same-snapshot restore safety."""

    @staticmethod
    def _headers(token):
        return {"Authorization": f"Bearer {token}"}

    def test_backup_contains_config_db_and_restores_without_overwriting_live_env(self, admin_token):
        headers = self._headers(admin_token)

        # Settings privacy/config regression before the destructive restore exercise.
        public_before = requests.get(f"{API}/settings", timeout=30)
        assert public_before.status_code == 200, public_before.text
        public_data = public_before.json()
        for private_key in ("opendrive_user", "opendrive_pass", "backup_schedule"):
            assert private_key not in public_data, f"Public settings leaked {private_key}"

        admin_before = requests.get(f"{API}/admin/settings", headers=headers, timeout=30)
        assert admin_before.status_code == 200, admin_before.text
        admin_data = admin_before.json()
        assert admin_data["opendrive_enabled"] is True, admin_data
        assert admin_data["backup_schedule"] == "daily", admin_data
        assert admin_data["has_opendrive_pass"] is True, admin_data
        assert "opendrive_pass" not in admin_data

        unauthorized = requests.get(f"{API}/admin/backup/download", timeout=30)
        assert unauthorized.status_code == 401, unauthorized.text

        downloaded = requests.get(
            f"{API}/admin/backup/download", headers=headers, timeout=120
        )
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.headers.get("content-type", "").startswith("application/zip")
        assert downloaded.content.startswith(b"PK")

        with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
            entries = archive.namelist()
            required = {
                "manifest.json",
                "config/backend.env",
                "config/frontend.env",
                "db/users.json",
                "db/hosts.json",
                "db/settings.json",
            }
            assert required.issubset(entries), sorted(required - set(entries))
            assert len(entries) == len(set(entries)), "Backup contains duplicate ZIP entries"
            assert all(not name.startswith("/") and ".." not in Path(name).parts for name in entries)

            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["config"] == ["backend.env", "frontend.env"], manifest
            for collection in ("users", "hosts", "settings"):
                assert collection in manifest["collections"], manifest
                assert isinstance(manifest["collections"][collection], int)
                assert manifest["collections"][collection] >= 1
                docs = json.loads(archive.read(f"db/{collection}.json"))
                assert isinstance(docs, list)
                assert len(docs) == manifest["collections"][collection]

            archived_backend_env = archive.read("config/backend.env")
            archived_frontend_env = archive.read("config/frontend.env")
            file_entries = [name for name in entries if name.startswith("files/") and not name.endswith("/")]
            assert manifest["files"] == len(file_entries), manifest

        live_backend_path = Path("/app/backend/.env")
        live_frontend_path = Path("/app/frontend/.env")
        live_backend_before = live_backend_path.read_bytes()
        live_frontend_before = live_frontend_path.read_bytes()
        backend_hash_before = hashlib.sha256(live_backend_before).hexdigest()
        frontend_hash_before = hashlib.sha256(live_frontend_before).hexdigest()

        restored = requests.post(
            f"{API}/admin/backup/restore",
            headers=headers,
            files={"file": ("fresh-current-backup.zip", downloaded.content, "application/zip")},
            timeout=180,
        )
        assert restored.status_code == 200, restored.text
        restore_data = restored.json()
        assert restore_data["ok"] is True, restore_data
        restored_counts = restore_data["restored"]
        assert restored_counts["_config_files"] == 2, restored_counts
        for collection in ("users", "hosts", "settings"):
            assert restored_counts[collection] == manifest["collections"][collection]

        assert hashlib.sha256(live_backend_path.read_bytes()).hexdigest() == backend_hash_before
        assert hashlib.sha256(live_frontend_path.read_bytes()).hexdigest() == frontend_hash_before
        assert live_backend_path.read_bytes() == live_backend_before
        assert live_frontend_path.read_bytes() == live_frontend_before
        assert Path("/app/backend/data/restored-config/backend.env").read_bytes() == archived_backend_env
        assert Path("/app/backend/data/restored-config/frontend.env").read_bytes() == archived_frontend_env

        # The original token/user survives, and both public API and another backup stay healthy.
        me_after = requests.get(f"{API}/auth/me", headers=headers, timeout=30)
        assert me_after.status_code == 200, me_after.text
        assert me_after.json()["email"] == ADMIN_EMAIL
        settings_after = requests.get(f"{API}/settings", timeout=30)
        assert settings_after.status_code == 200, settings_after.text
        for private_key in ("opendrive_user", "opendrive_pass", "backup_schedule"):
            assert private_key not in settings_after.json()

        admin_after = requests.get(f"{API}/admin/settings", headers=headers, timeout=30)
        assert admin_after.status_code == 200, admin_after.text
        assert admin_after.json()["opendrive_enabled"] is True
        assert admin_after.json()["backup_schedule"] == "daily"
        assert admin_after.json()["has_opendrive_pass"] is True
        assert "opendrive_pass" not in admin_after.json()

        second_download = requests.get(
            f"{API}/admin/backup/download", headers=headers, timeout=120
        )
        assert second_download.status_code == 200, second_download.text
        with zipfile.ZipFile(io.BytesIO(second_download.content)) as second_archive:
            assert "config/backend.env" in second_archive.namelist()
            assert "config/frontend.env" in second_archive.namelist()


    def test_preview_backup_has_no_non_media_restored_config_in_files_namespace(self, admin_token):
        response = requests.get(
            f"{API}/admin/backup/download", headers=self._headers(admin_token), timeout=120
        )
        assert response.status_code == 200, response.text
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            entries = archive.namelist()
            manifest = json.loads(archive.read("manifest.json"))
            file_entries = [name for name in entries if name.startswith("files/") and not name.endswith("/")]
        assert manifest["files"] == 0, manifest
        assert file_entries == [], file_entries

    def test_restore_rejects_config_path_traversal(self, admin_token):
        escaped = Path("/app/backend/TEST_restore_escape.txt")
        escaped.unlink(missing_ok=True)
        malicious = io.BytesIO()
        with zipfile.ZipFile(malicious, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps({"collections": {}}))
            archive.writestr("config/../../TEST_restore_escape.txt", b"TEST_ESCAPE")
        try:
            response = requests.post(
                f"{API}/admin/backup/restore",
                headers=self._headers(admin_token),
                files={"file": ("TEST_traversal.zip", malicious.getvalue(), "application/zip")},
                timeout=30,
            )
            assert response.status_code == 400, response.text
            assert not escaped.exists(), "Restore wrote outside BACKUP_DATA_DIR/restored-config"
        finally:
            escaped.unlink(missing_ok=True)


