from dotenv import load_dotenv
from pathlib import Path
import os

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import logging
import uuid
import asyncio
import secrets
import time
import json
import io
import zipfile
import pyzipper
import jwt
import bcrypt
import requests
import re
import socket
import ipaddress
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALGORITHM = "HS256"

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

def create_access_token(user_id: str, email: str) -> str:
    payload = {"sub": user_id, "email": email,
               "exp": datetime.now(timezone.utc) + timedelta(days=7), "type": "access"}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

# Cookies are Secure by default; set COOKIE_SECURE="false" only for plain-HTTP local dev.
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() != "false"

def set_auth_cookie(response: Response, token: str):
    response.set_cookie(key="access_token", value=token, httponly=True,
                        secure=COOKIE_SECURE, samesite="lax", max_age=604800, path="/")

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        if user.get("disabled"):
            raise HTTPException(status_code=403, detail="Account disabled")
        user["id"] = str(user["_id"])
        user.pop("_id", None)
        user.pop("password_hash", None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_admin_user(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class RegisterInput(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=6)
    turnstile_token: Optional[str] = None

class LoginInput(BaseModel):
    email: EmailStr
    password: str
    turnstile_token: Optional[str] = None

class Tier(BaseModel):
    name: str
    rate: float
    countries: List[str] = []

class HostInput(BaseModel):
    name: str
    domain: str
    default_rate: float = 5.0
    tiers: List[Tier] = []
    is_active: bool = True
    api_provider: Optional[str] = None
    api_key: Optional[str] = None
    login_email: Optional[str] = None
    login_password: Optional[str] = None

class HostLinkInput(BaseModel):
    host_id: str
    embed_url: str

class MirrorInput(BaseModel):
    title: str
    description: Optional[str] = ""
    links: List[HostLinkInput] = []

class TestKeyInput(BaseModel):
    api_provider: Optional[str] = None
    api_key: Optional[str] = None
    host_id: Optional[str] = None
    login_email: Optional[str] = None

class RefreshTiersInput(BaseModel):
    host_id: Optional[str] = None

class UserRoleInput(BaseModel):
    role: str

class UserDisabledInput(BaseModel):
    disabled: bool

class AdminCreateUserInput(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=6)
    role: str = "user"

class AdminPasswordInput(BaseModel):
    password: str = Field(min_length=6)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# Number of trusted reverse proxies (nginx/ingress) in front of the app. The real
# client IP is the entry appended by our own proxy, NOT the left-most (spoofable) one.
TRUSTED_PROXY_COUNT = int(os.environ.get("TRUSTED_PROXY_COUNT", "1"))

def get_client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            # Attackers can prepend a fake IP; our proxy appends the true peer to the
            # right, so index from the right past the trusted hops.
            idx = max(0, len(parts) - TRUSTED_PROXY_COUNT)
            return parts[idx]
    return request.client.host if request.client else "0.0.0.0"


def _is_public_host(url: str) -> bool:
    """SSRF guard: resolve the URL host and reject private/loopback/link-local/reserved
    targets so user-supplied embed URLs cannot probe internal services or cloud metadata."""
    try:
        u = urlparse(url if "://" in url else "https://" + url)
        if u.scheme not in ("http", "https"):
            return False
        host = u.hostname
        if not host:
            return False
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
                return False
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Cloudflare Turnstile (bot protection) — fully optional, keys stored in settings
# ---------------------------------------------------------------------------
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

async def _turnstile_cfg() -> dict:
    s = await db.settings.find_one({"key": "site"}) or {}
    return {
        "enabled": bool(s.get("turnstile_enabled")),
        "site_key": s.get("turnstile_site_key") or "",
        "secret_key": s.get("turnstile_secret_key") or "",
        "login": s.get("turnstile_login", True),
        "register": s.get("turnstile_register", True),
        "gate": s.get("turnstile_gate", True),
    }

def _turnstile_verify_sync(secret: str, token: str, ip: Optional[str]) -> bool:
    try:
        data = {"secret": secret, "response": token}
        if ip:
            data["remoteip"] = ip
        r = requests.post(TURNSTILE_VERIFY_URL, data=data, timeout=10)
        return bool(r.json().get("success"))
    except Exception as e:
        logger.warning(f"Turnstile verify error: {e}")
        return False

async def verify_turnstile(token: Optional[str], request: Request, surface: str) -> bool:
    """Returns True (allow) when Turnstile is disabled/unconfigured for this surface,
    otherwise validates the token with Cloudflare."""
    cfg = await _turnstile_cfg()
    if not cfg["enabled"] or not cfg["site_key"] or not cfg["secret_key"]:
        return True
    if not cfg.get(surface, True):
        return True
    if not token:
        return False
    return await asyncio.to_thread(_turnstile_verify_sync, cfg["secret_key"], token, get_client_ip(request))


# ---------------------------------------------------------------------------
# proxycheck.io VPN/Proxy detection — optional, key stored in settings, fail-open
# ---------------------------------------------------------------------------
def _proxycheck_sync(key: str, ip: str) -> dict:
    try:
        r = requests.get(f"https://proxycheck.io/v2/{ip}",
                          params={"key": key, "vpn": 1, "risk": 1}, timeout=(3, 5))
        d = r.json() if r.content else {}
        obj = d.get(ip, {}) if isinstance(d, dict) else {}
        is_proxy = str(obj.get("proxy", "")).lower() == "yes"
        return {"blocked": is_proxy, "enabled": True,
                "type": obj.get("type"), "risk": obj.get("risk")}
    except Exception as e:
        logger.warning(f"proxycheck failed: {type(e).__name__}")
        return {"blocked": False, "enabled": True, "fail_open": True}

async def vpn_check(ip: str) -> dict:
    """Returns {blocked: bool, ...}. Disabled/unconfigured -> not blocked. Fails open on errors.
    Results are cached for 24h to preserve the free daily quota."""
    s = await db.settings.find_one({"key": "site"}) or {}
    if not s.get("proxycheck_enabled") or not s.get("proxycheck_key"):
        return {"blocked": False, "enabled": False}
    if not _is_public_host(f"http://{ip}"):  # skip private/loopback IPs
        return {"blocked": False, "enabled": True}
    now = datetime.now(timezone.utc)
    cached = await db.proxycheck_cache.find_one({"ip": ip})
    if cached and cached.get("expires_at") and datetime.fromisoformat(cached["expires_at"]) > now:
        return cached["result"]
    result = await asyncio.to_thread(_proxycheck_sync, s.get("proxycheck_key"), ip)
    await db.proxycheck_cache.update_one(
        {"ip": ip},
        {"$set": {"ip": ip, "result": result, "expires_at": (now + timedelta(hours=24)).isoformat()}},
        upsert=True)
    return result

_geo_cache = {}

def geolocate(ip: str) -> dict:
    cached = _geo_cache.get(ip)
    if cached and time.time() - cached[1] < 3600:
        return cached[0]
    result = {"country_code": "XX", "country": "Unknown"}
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}?fields=status,countryCode,country", timeout=4)
        data = r.json()
        if data.get("status") == "success":
            result = {"country_code": data.get("countryCode", "XX"), "country": data.get("country", "Unknown")}
    except Exception as e:
        logger.warning(f"Geolocation failed for {ip}: {e}")
    _geo_cache[ip] = (result, time.time())
    return result

def rate_for_country(host: dict, country_code: str) -> float:
    for tier in host.get("tiers", []):
        if country_code in tier.get("countries", []):
            return float(tier["rate"])
    return float(host.get("default_rate", 0))

def probe_url(url: str):
    """Returns (status, final_url). status in 'online'/'offline'/'unknown'.
    Video hosts (Doodstream/VOE) sit behind Cloudflare/DDoS-Guard and return 403
    challenge pages to bots even when the video is live. We must NOT treat those as
    offline. Only definitive signals (404/410 or explicit not-found text) mean offline.
    final_url is the URL after following redirects (e.g. dsvplay.com -> playmogo.com).
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if not _is_public_host(url):
            return "unknown", url
        # Follow redirects manually so every hop is re-validated (blocks redirect-based SSRF).
        current = url
        r = None
        for _ in range(5):
            r = requests.get(current, timeout=10, headers=headers, allow_redirects=False)
            if r.status_code in (301, 302, 303, 307, 308):
                loc = r.headers.get("location")
                if not loc:
                    break
                nxt = requests.compat.urljoin(current, loc)
                if not _is_public_host(nxt):
                    return "unknown", current
                current = nxt
                continue
            break
        final_url = current or url
        code = r.status_code
        if code in (404, 410):
            return "offline", final_url
        body = r.text.lower()[:40000]
        challenge = ["just a moment", "ddos-guard", "checking your browser",
                     "cf-browser-verification", "attention required", "enable javascript and cookies"]
        if any(x in body for x in challenge):
            return "unknown", final_url
        if code == 200:
            not_found = ["file you are looking for", "file not found", "video not found",
                         "video has been deleted", "file has been removed", "no longer available",
                         "this video is unavailable", "404 not found", "file was deleted",
                         "video is unavailable"]
            if any(m in body for m in not_found):
                return "offline", final_url
            return "online", final_url
        # 403/429/503/5xx and anything else -> can't determine (assume protected/live)
        return "unknown", final_url
    except Exception:
        return "unknown", url



def normalize_embed_url(url: str) -> str:
    """Convert a pasted host URL into its /e/ embed form.
    e.g. voe.sx/xbel -> voe.sx/e/xbel ; dsvplay.com/d/abc -> dsvplay.com/e/abc
    """
    from urllib.parse import urlparse, urlunparse
    try:
        raw = url.strip()
        if not raw:
            return url
        u = urlparse(raw if "://" in raw else "https://" + raw)
        parts = [p for p in u.path.split("/") if p]
        if not parts:
            return url
        prefixes = {"d", "f", "v", "e", "embed"}
        if parts[0].lower() in prefixes:
            new_path = "/e/" + "/".join(parts[1:])
        elif len(parts) == 1:
            new_path = f"/e/{parts[0]}"
        else:
            return raw  # unknown pattern, leave untouched
        return urlunparse((u.scheme or "https", u.netloc, new_path, "", u.query, ""))
    except Exception:
        return url


async def enrich_host_links(links: List[dict]) -> List[dict]:
    host_ids = [l["host_id"] for l in links]
    hosts = {}
    async for h in db.hosts.find({"id": {"$in": host_ids}}):
        hosts[h["id"]] = h
    out = []
    for l in links:
        h = hosts.get(l["host_id"])
        if not h:
            continue
        item = dict(l)
        item["embed_url"] = normalize_embed_url(item.get("embed_url", ""))
        item["host_name"] = h["name"]
        item["host_domain"] = h["domain"]
        out.append(item)
    return out

def public_mirror(doc: dict) -> dict:
    doc = dict(doc)
    doc.pop("_id", None)
    return doc

def public_host(doc: dict) -> dict:
    """Serialize a host without leaking secrets (only whether they are set)."""
    doc = dict(doc)
    doc.pop("_id", None)
    key = doc.pop("api_key", None)
    doc["has_api_key"] = bool(key)
    pw = doc.pop("login_password", None)
    doc["has_login"] = bool(pw and doc.get("login_email"))
    return doc

# Fallback env vars used only when a host has no api_key stored in the DB.
KEY_ENV = {
    "doodstream": "DOODSTREAM_API_KEY",
    "voe": "VOE_API_KEY",
    "firestream": "FIRESTREAM_API_KEY",
}

def resolve_api_key(provider: Optional[str], host_key: Optional[str]) -> Optional[str]:
    if host_key:
        return host_key
    env_name = KEY_ENV.get(provider or "")
    return os.environ.get(env_name) if env_name else None

# ---------------------------------------------------------------------------
# Host API integrations (Doodstream + VOE)
# ---------------------------------------------------------------------------
DOOD_API = "https://doodapi.co/api"
_voe_domain_cache = {"prefix": None, "ts": 0.0}

def _api_json(url: str):
    r = requests.get(url, timeout=12, headers={"User-Agent": "MirrorStream/1.0"})
    return r.json()

def extract_file_code(url: str):
    from urllib.parse import urlparse
    try:
        u = urlparse(url if "://" in url else "https://" + url)
        parts = [p for p in u.path.split("/") if p]
        if not parts:
            return None
        if parts[0].lower() in {"e", "d", "f", "v", "embed"} and len(parts) > 1:
            return parts[1]
        return parts[-1]
    except Exception:
        return None

def voe_embed_prefix(key: Optional[str]):
    if not key:
        return None
    if _voe_domain_cache["prefix"] and time.time() - _voe_domain_cache["ts"] < 300:
        return _voe_domain_cache["prefix"]
    try:
        d = _api_json(f"https://voe.sx/api/settings/domain?key={key}")
        prefix = d.get("prefix_link_embed")
        if prefix:
            _voe_domain_cache["prefix"] = prefix
            _voe_domain_cache["ts"] = time.time()
            return prefix
    except Exception as e:
        logger.warning(f"VOE domain fetch failed: {e}")
    return _voe_domain_cache["prefix"]

def api_resolve_link(provider: str, embed_url: str, api_key: Optional[str] = None, login: Optional[str] = None):
    """Use the host's official API to get accurate status + a playable embed URL.
    Returns dict {status, url, title, thumbnail} or None to fall back to probe_url.
    """
    code = extract_file_code(embed_url)
    if not code:
        return None
    try:
        if provider == "doodstream":
            key = api_key
            if not key:
                return None
            chk = _api_json(f"{DOOD_API}/file/check?key={key}&file_code={code}")
            res = chk.get("result") or []
            active = bool(res) and str(res[0].get("status")).lower() == "active"
            info = _api_json(f"{DOOD_API}/file/info?key={key}&file_code={code}")
            ires = (info.get("result") or [{}])[0]
            # Use the canonical embed URL as-is (browser follows the redirect with
            # no-referrer, exactly like ListMirror). Do NOT bake in the rotating
            # abuse-domain, which serves X-Frame-Options to server-side probes.
            return {"status": "online" if active else "offline",
                    "url": embed_url, "title": ires.get("title"), "thumbnail": ires.get("splash_img")}
        if provider == "voe":
            key = api_key
            if not key:
                return None
            info = _api_json(f"https://voe.sx/api/file/info?key={key}&file_code={code}")
            ires = (info.get("result") or [{}])[0]
            online = ires.get("status") == 200
            prefix = voe_embed_prefix(key) or "https://voe.sx/e/"
            return {"status": "online" if online else "offline",
                    "url": f"{prefix}{code}", "title": ires.get("title"), "thumbnail": None}
        if provider == "firestream":
            key = api_key
            if not key:
                return None
            info = _api_json(f"https://firestream.to/api/file/info?key={key}&file_code={code}")
            ires = (info.get("result") or [{}])[0]
            online = ires.get("status") == 200 and ires.get("encoding_status") == "completed"
            return {"status": "online" if online else "offline",
                    "url": f"https://firestream.to/e/{code}",
                    "title": ires.get("title"), "thumbnail": None}
        if provider == "playmate":
            if not api_key:
                return None
            info = _api_json(f"https://api.playmate.to/file/info?key={api_key}&file_code={code}")
            ires = (info.get("result") or [{}])[0]
            online = ires.get("status") == 200 and str(ires.get("canplay")) in ("1", "True", "true")
            return {"status": "online" if online else "offline",
                    "url": f"https://playmate.to/e/{code}",
                    "title": ires.get("name") or ires.get("title"), "thumbnail": None}
        if provider == "vidara":
            if not api_key:
                return None
            info = _api_json(f"https://api.vidara.so/v1/video/info?api_key={api_key}&filecode={code}")
            res = info.get("result")
            ires = (res[0] if isinstance(res, list) else res) or {}
            online = str(ires.get("status")) in ("200", "active") or str(ires.get("canplay")) in ("1", "True", "true")
            return {"status": "online" if online else "offline",
                    "url": f"https://vidara.so/e/{code}",
                    "title": ires.get("title") or ires.get("name"), "thumbnail": None}
        if provider == "streamtape":
            if not (api_key and login):
                return None
            info = _api_json(f"https://api.streamtape.com/file/info?file={code}&login={login}&key={api_key}")
            res = info.get("result") or {}
            entry = res.get(code) if isinstance(res, dict) else None
            online = bool(entry) and entry.get("status") == 200
            return {"status": "online" if online else "offline",
                    "url": f"https://streamtape.com/e/{code}",
                    "title": (entry or {}).get("name"), "thumbnail": None}
        if provider == "vinovo":
            if not api_key:
                return None
            info = _api_json(f"https://api.vinovo.si/api/file/info?key={api_key}&file_code={code}")
            res = info.get("result") or []
            ires = (res[0] if isinstance(res, list) else res) or {}
            st = str(ires.get("status"))
            online = st in ("200", "Active") or str(ires.get("canplay")) in ("1", "True", "true")
            return {"status": "online" if online else "offline",
                    "url": f"https://vinovo.si/e/{code}",
                    "title": ires.get("title") or ires.get("name"), "thumbnail": ires.get("single_img")}
        if provider == "vidnest":
            if not api_key:
                return None
            info = _api_json(f"https://vidnest.io/api/file/info?key={api_key}&file_code={code}")
            res = info.get("result") or []
            ires = (res[0] if isinstance(res, list) else res) or {}
            online = ires.get("status") == 200 and str(ires.get("canplay")) in ("1", "True", "true")
            return {"status": "online" if online else "offline",
                    "url": f"https://vidnest.io/e/{code}",
                    "title": ires.get("file_title") or ires.get("title"), "thumbnail": ires.get("player_img")}
    except Exception as e:
        logger.warning(f"api_resolve_link {provider} failed: {e}")
    return None

def validate_api_key(provider: Optional[str], key: Optional[str], login: Optional[str] = None) -> dict:
    """Check a hoster API key against the provider's account endpoint. Never returns the key."""
    if not key:
        return {"ok": False, "message": "No API key set"}
    try:
        if provider == "doodstream":
            d = _api_json(f"{DOOD_API}/account/info?key={key}")
            r = d.get("result") or {}
            if d.get("status") == 200 and r:
                return {"ok": True, "message": "Valid key", "email": r.get("email"), "balance": r.get("balance")}
            return {"ok": False, "message": d.get("msg") or "Invalid key"}
        if provider == "voe":
            d = _api_json(f"https://voe.sx/api/settings/domain?key={key}")
            if d.get("status") == 200 or d.get("success"):
                return {"ok": True, "message": "Valid key", "email": None, "balance": None}
            return {"ok": False, "message": "Invalid key"}
        if provider == "firestream":
            d = _api_json(f"https://firestream.to/api/account/info?key={key}")
            r = d.get("result") or {}
            if d.get("status") == 200 and r:
                return {"ok": True, "message": "Valid key", "email": r.get("email"), "balance": r.get("balance")}
            return {"ok": False, "message": d.get("msg") or "Invalid key"}
        if provider in ("playmate", "vinovo", "vidnest"):
            base = {"playmate": "https://api.playmate.to", "vinovo": "https://api.vinovo.si/api",
                    "vidnest": "https://vidnest.io/api"}[provider]
            d = _api_json(f"{base}/account/info?key={key}")
            r = d.get("result") or {}
            if d.get("status") == 200 and r:
                return {"ok": True, "message": "Valid key", "email": r.get("email"), "balance": r.get("balance")}
            return {"ok": False, "message": d.get("msg") or "Invalid key"}
        if provider == "vidara":
            d = _api_json(f"https://api.vidara.so/v1/user/info?api_key={key}")
            r = d.get("result") or {}
            if d.get("status") == 200 and r:
                return {"ok": True, "message": "Valid key", "email": r.get("email"), "balance": r.get("balance")}
            return {"ok": False, "message": d.get("msg") or "Invalid key"}
        if provider == "streamtape":
            if not login:
                return {"ok": False, "message": "Streamtape needs API-Login + API-Key"}
            d = _api_json(f"https://api.streamtape.com/account/info?login={login}&key={key}")
            r = d.get("result") or {}
            if d.get("status") == 200 and r:
                return {"ok": True, "message": "Valid key", "email": r.get("email"), "balance": None}
            return {"ok": False, "message": d.get("msg") or "Invalid login/key"}
        return {"ok": False, "message": "No key validation available for this provider"}
    except Exception as e:
        # Never surface the raw exception: request URLs contain the API key.
        logger.warning(f"validate_api_key {provider} failed: {type(e).__name__}")
        return {"ok": False, "message": "Request failed. Please check the key and try again."}


# ---------------------------------------------------------------------------
# Earning-tier auto-update (scrape hosters' public earn pages)
# ---------------------------------------------------------------------------
_SCRAPE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# Full country name -> ISO alpha-2 (covers the names used on the VOE earn page + common ones).
NAME_TO_ISO = {
    "australia": "AU", "united kingdom": "GB", "united states": "US", "germany": "DE",
    "austria": "AT", "canada": "CA", "denmark": "DK", "finland": "FI", "norway": "NO",
    "bulgaria": "BG", "switzerland": "CH", "spain": "ES", "croatia": "HR", "ireland": "IE",
    "italy": "IT", "netherlands": "NL", "new zealand": "NZ", "sweden": "SE", "thailand": "TH",
    "belgium": "BE", "poland": "PL", "bosnia and herzegovina": "BA", "brazil": "BR",
    "chile": "CL", "cyprus": "CY", "czech republic": "CZ", "czechia": "CZ", "greece": "GR",
    "hong kong": "HK", "japan": "JP", "mexico": "MX", "romania": "RO", "serbia": "RS",
    "united arab emirates": "AE", "hungary": "HU", "malaysia": "MY", "vietnam": "VN",
    "france": "FR", "portugal": "PT", "south korea": "KR", "korea": "KR", "singapore": "SG",
    "india": "IN", "indonesia": "ID", "russia": "RU", "turkey": "TR", "south africa": "ZA",
    "slovakia": "SK", "argentina": "AR", "colombia": "CO", "peru": "PE", "egypt": "EG",
    "pakistan": "PK", "philippines": "PH", "ukraine": "UA", "israel": "IL", "china": "CN",
    "slovenia": "SI", "lithuania": "LT", "latvia": "LV", "estonia": "EE", "luxembourg": "LU",
    "russian federation": "RU", "russia": "RU", "slovak republic": "SK", "czech republic": "CZ",
    "usa": "US", "uk": "GB", "united states of america": "US", "philipines": "PH",
    "bosnia-herzegovina": "BA", "bosnia herzegovina": "BA",
}

def _name_to_iso(name: str):
    return NAME_TO_ISO.get(name.strip().lower())

def scrape_voe_tiers():
    """Parse https://voe.sx/earn-money (server-rendered). Returns (tiers, default_rate)."""
    html = requests.get("https://voe.sx/earn-money", timeout=15, headers=_SCRAPE_HEADERS).text
    lines = [re.sub(r"\s+", " ", l).strip() for l in re.sub(r"<[^>]+>", "\n", html).split("\n")]
    lines = [l for l in lines if l]
    tiers, default_rate = [], None
    current_rate = None
    current_countries = []
    def flush():
        nonlocal current_rate, current_countries
        if current_rate is not None and current_countries:
            tiers.append({"name": f"Tier {len(tiers)+1}", "rate": current_rate,
                          "countries": current_countries})
        current_countries = []
    started = False
    for l in lines:
        m = re.fullmatch(r"\$(\d+(?:\.\d+)?)", l)
        if m:
            started = True
            flush()
            current_rate = float(m.group(1))
            continue
        if not started:
            continue
        if l.lower().startswith("all other"):
            # remaining rate is the default; stop after
            default_rate = current_rate
            current_rate = None
            break
        if current_rate is not None:
            iso = _name_to_iso(l)
            if iso:
                current_countries.append(iso)
            elif len(current_countries) > 0 and not re.match(r"^[A-Z]", l):
                # hit non-country text -> end of tier block
                flush()
                current_rate = None
    flush()
    return tiers, default_rate

def scrape_firestream_tiers():
    """Parse FireStream tier data embedded in the SPA JS bundle. Returns (tiers, default_rate)."""
    home = requests.get("https://firestream.to/", timeout=15, headers=_SCRAPE_HEADERS).text
    m = re.search(r"assets/index-[A-Za-z0-9_\-]+\.js", home)
    if not m:
        return [], None
    js = requests.get(f"https://firestream.to/{m.group(0)}", timeout=20, headers=_SCRAPE_HEADERS).text
    found = re.findall(r'\{name:"(Tier \d+)",rate:(\d+(?:\.\d+)?),countries:"([^"]+)"', js)
    tiers, default_rate = [], None
    for name, rate, countries in found:
        codes = [c.strip().upper() for c in countries.split(",")]
        if all(re.fullmatch(r"[A-Z]{2}", c) for c in codes):
            tiers.append({"name": f"Tier {len(tiers)+1}", "rate": float(rate), "countries": codes})
        else:
            # "All other countries" style -> default rate
            default_rate = float(rate)
    return tiers, default_rate

def scrape_doodstream_tiers():
    """Parse https://doodstream.co/earn-money. Tiers 1-4 live in JS vars; Tier 5 + default in text."""
    html = requests.get("https://doodstream.co/earn-money", timeout=15, headers=_SCRAPE_HEADERS).text
    countries = dict(re.findall(r'data_countries(\d+)="([^"]*)"', html))
    amounts = dict(re.findall(r'data_amount(\d+)="([^"]*)"', html))
    tiers, default_rate = [], None
    for n in sorted(countries.keys(), key=lambda x: int(x)):
        names = [c.strip() for c in countries[n].split(",") if c.strip()]
        codes = [c for c in (_name_to_iso(x) for x in names) if c]
        rate_raw = (amounts.get(n, "0").split(",")[0] or "0")
        try:
            rate = float(rate_raw)
        except ValueError:
            rate = 0.0
        if codes and rate:
            tiers.append({"name": f"Tier {len(tiers)+1}", "rate": rate, "countries": codes})
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    m5 = re.search(r"Tier 5\s+([A-Za-z ]+?)\s*\$\s*([\d.]+)", text)
    if m5:
        iso = _name_to_iso(m5.group(1))
        if iso:
            tiers.append({"name": f"Tier {len(tiers)+1}", "rate": float(m5.group(2)), "countries": [iso]})
    md = re.search(r"All Others.{0,40}?\$\s*([\d.]+)", text)
    if md:
        default_rate = float(md.group(1))
    return tiers, default_rate

TIER_SCRAPERS = {"voe": scrape_voe_tiers, "firestream": scrape_firestream_tiers,
                 "doodstream": scrape_doodstream_tiers}


# --- New hosters: earn-page tier scrapers -------------------------------------
_ISO_KEYS_SORTED = sorted(NAME_TO_ISO.keys(), key=len, reverse=True)

def _codes_in_text(text: str) -> List[str]:
    low = text.lower()
    found = []
    for name in _ISO_KEYS_SORTED:
        if re.search(r"\b" + re.escape(name) + r"\b", low):
            code = NAME_TO_ISO[name]
            if code not in found:
                found.append(code)
    return found

def _scrape_tier_blocks(url: str):
    """Generic parser for earn pages that list 'Tier N' blocks, each with a $rate and
    a set of country names. Returns (tiers, default_rate)."""
    html = requests.get(url, timeout=15, headers=_SCRAPE_HEADERS).text
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    chunks = re.split(r"(?i)\btier\s*\d+\b", text)
    tiers = []
    for chunk in chunks[1:]:
        seg = re.split(r"(?i)all\s*others|\bothers\b|rules|minimum payout|conditions|referral", chunk)[0]
        mamt = re.search(r"\$\s*([\d.]+)", seg)
        if not mamt:
            continue
        rate = float(mamt.group(1))
        codes = _codes_in_text(seg)
        if codes and rate:
            tiers.append({"rate": rate, "countries": codes})
    tiers = [{"name": f"Tier {i+1}", "rate": t["rate"], "countries": t["countries"]}
             for i, t in enumerate(tiers)]
    md = re.search(r"(?i)(?:all\s*others|every other country[^$]{0,80}?)\$\s*([\d.]+)", text)
    default_rate = float(md.group(1)) if md else None
    return tiers, default_rate

def scrape_vidara_tiers():
    return _scrape_tier_blocks("https://vidara.so/earn")

def scrape_vinovo_tiers():
    return _scrape_tier_blocks("https://vinovo.si/affiliate")

def scrape_vidnest_tiers():
    return _scrape_tier_blocks("https://vidnest.io/earn")

# Note: Playmate's earn table is rendered client-side and not present in the raw HTML,
# so it can't be scraped server-side; its tiers stay as seeded (admin-editable).
TIER_SCRAPERS.update({
    "vidara": scrape_vidara_tiers,
    "vinovo": scrape_vinovo_tiers,
    "vidnest": scrape_vidnest_tiers,
})

async def refresh_host_tiers(host: dict) -> dict:
    prov = host.get("api_provider")
    fn = TIER_SCRAPERS.get(prov or "")
    if not fn:
        return {"host_id": host.get("id"), "name": host.get("name"), "ok": False,
                "message": "No public tier source for this host"}
    try:
        tiers, default_rate = await asyncio.to_thread(fn)
        if not tiers:
            return {"host_id": host.get("id"), "name": host.get("name"), "ok": False,
                    "message": "Could not parse any tiers"}
        update = {"tiers": tiers, "tiers_updated_at": now_iso()}
        if default_rate is not None:
            update["default_rate"] = default_rate
        await db.hosts.update_one({"id": host["id"]}, {"$set": update})
        return {"host_id": host.get("id"), "name": host.get("name"), "ok": True, "count": len(tiers)}
    except Exception as e:
        logger.warning(f"refresh_host_tiers {host.get('name')} failed: {e}")
        return {"host_id": host.get("id"), "name": host.get("name"), "ok": False, "message": str(e)}


# ---------------------------------------------------------------------------
# Auto-fix offline links (find a re-uploaded file with the same name)
# ---------------------------------------------------------------------------
_VIDEO_EXT = re.compile(r"\.(mp4|mkv|avi|mov|webm|wmv|flv|m4v|ts)$", re.I)

def _norm_title(s: str) -> str:
    if not s:
        return ""
    return _VIDEO_EXT.sub("", s.strip()).strip().lower()

def _dood_search_term(title: str) -> str:
    """Doodstream search chokes on punctuation like '()'. Use the part before the first
    bracket, stripped of punctuation, as a broad query and match exactly client-side."""
    t = _VIDEO_EXT.sub("", title or "")
    t = re.split(r"[(\[]", t)[0]
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t or _norm_title(title)

def _firestream_search(email: str, password: str, api_key: str, target: str):
    """Log into FireStream (cookie session) and find the newest ONLINE video matching `target`."""
    if not email or not password:
        return None
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    lr = s.post("https://firestream.to/api/auth/login",
                json={"email": email, "password": password}, timeout=20)
    if lr.status_code != 200:
        return None
    matches, page = [], 1
    while page <= 6:
        r = s.get(f"https://firestream.to/api/videos?page={page}", timeout=20)
        if r.status_code != 200:
            break
        d = r.json()
        for v in d.get("videos", []):
            if _norm_title(v.get("title") or v.get("originalName", "")) == target:
                matches.append(v)
        if not d.get("hasNext"):
            break
        page += 1
    if not matches:
        return None
    matches.sort(key=lambda v: v.get("createdAt", ""), reverse=True)
    for v in matches:
        slug = v.get("slug")
        if not slug:
            continue
        url = f"https://firestream.to/e/{slug}"
        info = api_resolve_link("firestream", url, api_key) if api_key else None
        if info and info.get("status") == "online":
            return {"url": url, "title": v.get("title"), "code": slug}
        if not api_key and v.get("status") == "active" and v.get("encodingStatus") in ("completed", "ready"):
            return {"url": url, "title": v.get("title"), "code": slug}
    return None

def find_replacement(provider: str, key: str, title: str, host: Optional[dict] = None):
    """Search the hoster account for the newest ONLINE file whose name matches `title`."""
    target = _norm_title(title)
    if not target or not key:
        return None
    try:
        if provider == "doodstream":
            term = _dood_search_term(title)
            d = _api_json(f"{DOOD_API}/search/videos?key={key}&search_term={requests.utils.quote(term)}")
            results = d.get("result") or []
            online = [r for r in results if _norm_title(r.get("title", "")) == target
                      and str(r.get("canplay")) in ("1", "True", "true")]
            if not online:
                return None
            online.sort(key=lambda r: r.get("uploaded", ""), reverse=True)
            code = online[0].get("file_code")
            return {"url": f"https://doodstream.com/e/{code}",
                    "title": online[0].get("title"), "code": code}
        if provider == "voe":
            d = _api_json(f"https://voe.sx/api/file/list?key={key}&per_page=250")
            data = ((d.get("result") or {}).get("data")) or []
            matches = [r for r in data if _norm_title(r.get("title") or r.get("name", "")) == target]
            matches.sort(key=lambda r: r.get("uploaded", ""), reverse=True)
            prefix = voe_embed_prefix(key) or "https://voe.sx/e/"
            for r in matches:
                code = r.get("filecode") or r.get("file_code")
                # Confirm the candidate is actually online before using it.
                info = api_resolve_link("voe", f"{prefix}{code}", key)
                if info and info.get("status") == "online":
                    return {"url": info.get("url") or f"{prefix}{code}",
                            "title": r.get("title"), "code": code}
            return None
        if provider == "firestream":
            h = host or {}
            return _firestream_search(h.get("login_email"), h.get("login_password"), key, target)
        if provider in ("playmate", "vidara", "vinovo", "vidnest"):
            q = requests.utils.quote(_dood_search_term(title))
            if provider == "playmate":
                d = _api_json(f"https://api.playmate.to/file/search?key={key}&q={q}&per_page=100")
                data = d.get("result") or []
                embed = "https://playmate.to/e/"
            elif provider == "vidara":
                d = _api_json(f"https://api.vidara.so/v1/video/list?api_key={key}&title={q}&limit=200")
                res = d.get("result") or {}
                data = res.get("files") if isinstance(res, dict) else res
                embed = "https://vidara.so/e/"
            elif provider == "vinovo":
                d = _api_json(f"https://api.vinovo.si/api/file/list?key={key}&search_term={q}&per_page=200")
                data = (d.get("result") or {}).get("files") or []
                embed = "https://vinovo.si/e/"
            else:  # vidnest
                d = _api_json(f"https://vidnest.io/api/file/list?key={key}&title={q}&per_page=200")
                data = (d.get("result") or {}).get("files") or []
                embed = "https://vidnest.io/e/"
            data = data or []
            matches = [r for r in data if _norm_title(r.get("title") or r.get("name") or r.get("file_title", "")) == target]
            matches.sort(key=lambda r: r.get("uploaded", ""), reverse=True)
            for r in matches:
                c = r.get("filecode") or r.get("file_code")
                if not c:
                    continue
                info = api_resolve_link(provider, f"{embed}{c}", key)
                if info and info.get("status") == "online":
                    return {"url": info.get("url") or f"{embed}{c}",
                            "title": r.get("title") or r.get("name") or r.get("file_title"), "code": c}
            return None
        if provider == "streamtape":
            h = host or {}
            login = h.get("login_email")
            if not login:
                return None
            d = _api_json(f"https://api.streamtape.com/file/listfolder?login={login}&key={key}")
            files = ((d.get("result") or {}).get("files")) or []
            matches = [r for r in files if _norm_title(r.get("name", "")) == target and r.get("convert") == "converted"]
            matches.sort(key=lambda r: r.get("created_at", 0), reverse=True)
            if matches:
                c = matches[0].get("linkid")
                return {"url": f"https://streamtape.com/e/{c}", "title": matches[0].get("name"), "code": c}
            return None
    except Exception as e:
        logger.warning(f"find_replacement {provider} failed: {e}")
    return None


async def resolve_mirror_links(mirror_id: str):
    """Background/on-demand: use host APIs (or HTTP probe) to set status + resolved playable url."""
    try:
        m = await db.mirrors.find_one({"id": mirror_id})
        if not m:
            return
        links = m.get("links", [])
        host_ids = [l["host_id"] for l in links]
        providers = {}
        async for h in db.hosts.find({"id": {"$in": host_ids}}):
            providers[h["id"]] = (h.get("api_provider"), resolve_api_key(h.get("api_provider"), h.get("api_key")), h.get("login_email"))
        for l in links:
            prov, key, login = providers.get(l["host_id"], (None, None, None))
            api = await asyncio.to_thread(api_resolve_link, prov, l["embed_url"], key, login) if prov else None
            if api:
                l["status"] = api["status"]
                l["resolved_url"] = api["url"]
                if api.get("title"):
                    l["title"] = api["title"]
                if api.get("thumbnail"):
                    l["thumbnail"] = api["thumbnail"]
            else:
                result, final_url = await asyncio.to_thread(probe_url, l["embed_url"])
                l["status"] = "online" if result == "unknown" else result
                l["resolved_url"] = final_url
            l["last_checked"] = now_iso()
        await db.mirrors.update_one({"id": mirror_id}, {"$set": {"links": links}})
    except Exception as e:
        logger.warning(f"resolve_mirror_links failed for {mirror_id}: {e}")


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------
@api_router.post("/auth/register")
async def register(inp: RegisterInput, request: Request, response: Response):
    if not await verify_turnstile(inp.turnstile_token, request, "register"):
        raise HTTPException(status_code=400, detail="Bot verification failed. Please try again.")
    ip = get_client_ip(request)
    ip_ident = f"register:{ip}"
    ip_attempt = await db.login_attempts.find_one({"identifier": ip_ident})
    if ip_attempt and ip_attempt.get("count", 0) >= 10:
        locked = ip_attempt.get("locked_until")
        if locked and datetime.fromisoformat(locked) > datetime.now(timezone.utc):
            raise HTTPException(status_code=429, detail="Too many sign-ups from this network. Try again later.")
    await db.login_attempts.update_one(
        {"identifier": ip_ident},
        {"$inc": {"count": 1},
         "$set": {"locked_until": (datetime.now(timezone.utc) + timedelta(minutes=60)).isoformat()}},
        upsert=True)
    email = inp.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    doc = {"email": email, "name": inp.name, "password_hash": hash_password(inp.password),
           "role": "user", "created_at": now_iso()}
    res = await db.users.insert_one(doc)
    uid = str(res.inserted_id)
    token = create_access_token(uid, email)
    set_auth_cookie(response, token)
    return {"access_token": token, "user": {"id": uid, "email": email, "name": inp.name, "role": "user"}}

@api_router.post("/auth/login")
async def login(inp: LoginInput, request: Request, response: Response):
    if not await verify_turnstile(inp.turnstile_token, request, "login"):
        raise HTTPException(status_code=400, detail="Bot verification failed. Please try again.")
    email = inp.email.lower()
    ip = get_client_ip(request)
    ident = f"{ip}:{email}"
    ip_ident = f"ip:{ip}"
    now = datetime.now(timezone.utc)

    def _locked(doc, limit):
        if doc and doc.get("count", 0) >= limit:
            locked = doc.get("locked_until")
            if locked and datetime.fromisoformat(locked) > now:
                return True
        return False

    attempt = await db.login_attempts.find_one({"identifier": ident})
    ip_attempt = await db.login_attempts.find_one({"identifier": ip_ident})
    # Per-account (5) and per-IP across all accounts (20, blocks password spraying).
    if _locked(attempt, 5) or _locked(ip_attempt, 20):
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(inp.password, user["password_hash"]):
        for key, mins in ((ident, 15), (ip_ident, 15)):
            await db.login_attempts.update_one(
                {"identifier": key},
                {"$inc": {"count": 1},
                 "$set": {"locked_until": (now + timedelta(minutes=mins)).isoformat()}},
                upsert=True)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    await db.login_attempts.delete_one({"identifier": ident})
    await db.login_attempts.delete_one({"identifier": ip_ident})
    if user.get("disabled"):
        raise HTTPException(status_code=403, detail="This account has been disabled")
    uid = str(user["_id"])
    token = create_access_token(uid, email)
    set_auth_cookie(response, token)
    return {"access_token": token,
            "user": {"id": uid, "email": email, "name": user.get("name"), "role": user.get("role", "user")}}

@api_router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"message": "Logged out"}

class GateInput(BaseModel):
    token: Optional[str] = None

@api_router.post("/security/verify-gate")
async def verify_gate(inp: GateInput, request: Request):
    if not await verify_turnstile(inp.token, request, "gate"):
        raise HTTPException(status_code=400, detail="Bot verification failed. Please try again.")
    return {"ok": True}

@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user


# ---------------------------------------------------------------------------
# Host endpoints
# ---------------------------------------------------------------------------
@api_router.get("/hosts")
async def list_hosts(user: dict = Depends(get_current_user)):
    hosts = await db.hosts.find({}).to_list(500)
    return [public_host(h) for h in hosts]

@api_router.post("/hosts")
async def create_host(inp: HostInput, admin: dict = Depends(get_admin_user)):
    doc = inp.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = now_iso()
    await db.hosts.insert_one(doc)
    return public_host(doc)

@api_router.put("/hosts/{host_id}")
async def update_host(host_id: str, inp: HostInput, admin: dict = Depends(get_admin_user)):
    existing = await db.hosts.find_one({"id": host_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Host not found")
    update = inp.model_dump()
    # Blank secrets mean "keep the existing value" (raw secrets are never sent back to the UI).
    if not update.get("api_key"):
        update.pop("api_key", None)
    if not update.get("login_password"):
        update.pop("login_password", None)
    await db.hosts.update_one({"id": host_id}, {"$set": update})
    updated = await db.hosts.find_one({"id": host_id})
    return public_host(updated)

@api_router.post("/hosts/test-key")
async def test_host_key(inp: TestKeyInput, admin: dict = Depends(get_admin_user)):
    provider = inp.api_provider
    key = inp.api_key
    login = inp.login_email
    if inp.host_id:
        h = await db.hosts.find_one({"id": inp.host_id})
        if h:
            provider = provider or h.get("api_provider")
            login = login or h.get("login_email")
            if not key:
                key = resolve_api_key(h.get("api_provider"), h.get("api_key"))
    if not key:
        key = resolve_api_key(provider, None)
    return await asyncio.to_thread(validate_api_key, provider, key, login)

@api_router.post("/admin/hosts/refresh-tiers")
async def refresh_tiers(inp: RefreshTiersInput, admin: dict = Depends(get_admin_user)):
    if inp.host_id:
        hosts = await db.hosts.find({"id": inp.host_id}).to_list(1)
    else:
        hosts = await db.hosts.find({"api_provider": {"$in": list(TIER_SCRAPERS.keys())}}).to_list(100)
    results = []
    for h in hosts:
        results.append(await refresh_host_tiers(h))
    return {"results": results}

@api_router.delete("/hosts/{host_id}")
async def delete_host(host_id: str, admin: dict = Depends(get_admin_user)):
    await db.hosts.delete_one({"id": host_id})
    return {"message": "Host deleted"}


# ---------------------------------------------------------------------------
# Mirror endpoints
# ---------------------------------------------------------------------------
@api_router.get("/mirrors")
async def list_mirrors(user: dict = Depends(get_current_user)):
    query = {} if user.get("role") == "admin" else {"created_by": user["id"]}
    mirrors = await db.mirrors.find(query).sort("created_at", -1).to_list(1000)
    return [public_mirror(m) for m in mirrors]

@api_router.post("/mirrors")
async def create_mirror(inp: MirrorInput, user: dict = Depends(get_current_user)):
    links = await enrich_host_links([l.model_dump() for l in inp.links])
    for l in links:
        l["status"] = "pending"
        l["last_checked"] = None
    doc = {
        "id": str(uuid.uuid4()),
        "slug": secrets.token_urlsafe(6),
        "title": inp.title,
        "description": inp.description or "",
        "links": links,
        "created_by": user["id"],
        "creator_name": user.get("name"),
        "views": 0,
        "created_at": now_iso(),
    }
    await db.mirrors.insert_one(doc)
    asyncio.create_task(resolve_mirror_links(doc["id"]))
    return public_mirror(doc)

@api_router.get("/mirrors/{mirror_id}")
async def get_mirror(mirror_id: str, user: dict = Depends(get_current_user)):
    m = await db.mirrors.find_one({"id": mirror_id})
    if not m:
        raise HTTPException(status_code=404, detail="Mirror not found")
    if user.get("role") != "admin" and m["created_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not allowed")
    return public_mirror(m)

@api_router.put("/mirrors/{mirror_id}")
async def update_mirror(mirror_id: str, inp: MirrorInput, user: dict = Depends(get_current_user)):
    m = await db.mirrors.find_one({"id": mirror_id})
    if not m:
        raise HTTPException(status_code=404, detail="Mirror not found")
    if user.get("role") != "admin" and m["created_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not allowed")
    links = await enrich_host_links([l.model_dump() for l in inp.links])
    existing_status = {l["host_id"]: l for l in m.get("links", [])}
    for l in links:
        prev = existing_status.get(l["host_id"])
        unchanged = prev and prev.get("embed_url") == l["embed_url"]
        l["status"] = prev["status"] if unchanged else "pending"
        l["last_checked"] = prev["last_checked"] if unchanged else None
        l["resolved_url"] = prev.get("resolved_url") if unchanged else None
    await db.mirrors.update_one({"id": mirror_id},
                                {"$set": {"title": inp.title, "description": inp.description or "", "links": links}})
    asyncio.create_task(resolve_mirror_links(mirror_id))
    updated = await db.mirrors.find_one({"id": mirror_id})
    return public_mirror(updated)

@api_router.delete("/mirrors/{mirror_id}")
async def delete_mirror(mirror_id: str, user: dict = Depends(get_current_user)):
    m = await db.mirrors.find_one({"id": mirror_id})
    if not m:
        raise HTTPException(status_code=404, detail="Mirror not found")
    if user.get("role") != "admin" and m["created_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not allowed")
    await db.mirrors.delete_one({"id": mirror_id})
    await db.views.delete_many({"mirror_id": mirror_id})
    return {"message": "Mirror deleted"}

@api_router.post("/mirrors/{mirror_id}/check")
async def check_mirror(mirror_id: str, user: dict = Depends(get_current_user)):
    m = await db.mirrors.find_one({"id": mirror_id})
    if not m:
        raise HTTPException(status_code=404, detail="Mirror not found")
    if user.get("role") != "admin" and m["created_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not allowed")
    await resolve_mirror_links(mirror_id)
    updated = await db.mirrors.find_one({"id": mirror_id})
    return public_mirror(updated)


@api_router.post("/mirrors/{mirror_id}/autofix/{host_id}")
async def autofix_link(mirror_id: str, host_id: str, user: dict = Depends(get_current_user)):
    m = await db.mirrors.find_one({"id": mirror_id})
    if not m:
        raise HTTPException(status_code=404, detail="Mirror not found")
    if user.get("role") != "admin" and m["created_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not allowed")
    link = next((l for l in m.get("links", []) if l["host_id"] == host_id), None)
    if not link:
        raise HTTPException(status_code=404, detail="Host link not found")
    host = await db.hosts.find_one({"id": host_id})
    if not host:
        raise HTTPException(status_code=404, detail="Host not found")
    provider = host.get("api_provider")
    AUTOFIX_PROVIDERS = ("doodstream", "voe", "firestream", "playmate", "vidara", "streamtape", "vinovo", "vidnest")
    if provider not in AUTOFIX_PROVIDERS:
        raise HTTPException(status_code=400, detail="Auto-fix is not supported for this host")
    if provider == "firestream" and not (host.get("login_email") and host.get("login_password")):
        raise HTTPException(status_code=400, detail="FireStream login not configured")
    if provider == "streamtape" and not host.get("login_email"):
        raise HTTPException(status_code=400, detail="Streamtape API-Login not configured")
    key = resolve_api_key(provider, host.get("api_key"))
    title = link.get("title") or m.get("title")
    rep = await asyncio.to_thread(find_replacement, provider, key, title, host)

    async def _log(status, new_url=None, reason=None, new_title=None):
        await db.fix_logs.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": m["created_by"],
            "mirror_id": mirror_id,
            "mirror_title": m.get("title"),
            "slug": m.get("slug"),
            "host_id": host_id,
            "host_name": host.get("name"),
            "status": status,
            "new_url": new_url,
            "reason": reason,
            "title": new_title,
            "created_at": now_iso(),
        })

    if not rep:
        reason = "No matching online file found in your account"
        await _log("failed", reason=reason)
        return {"ok": False, "message": reason}
    link["embed_url"] = rep["url"]
    link["resolved_url"] = rep["url"]
    link["status"] = "online"
    if rep.get("title"):
        link["title"] = rep["title"]
    link["last_checked"] = now_iso()
    await db.mirrors.update_one({"id": mirror_id}, {"$set": {"links": m["links"]}})
    await _log("success", new_url=rep["url"], new_title=rep.get("title"))
    return {"ok": True, "new_url": rep["url"], "title": rep.get("title")}


@api_router.get("/fix-logs")
async def fix_logs(user: dict = Depends(get_current_user)):
    query = {} if user.get("role") == "admin" else {"user_id": user["id"]}
    logs = await db.fix_logs.find(query).sort("created_at", -1).to_list(100)
    return [public_mirror(l) for l in logs]


# ---------------------------------------------------------------------------
# Public embed endpoint
# ---------------------------------------------------------------------------
def _links_stale(links: List[dict], max_age: int) -> bool:
    now = datetime.now(timezone.utc)
    for l in links:
        lc = l.get("last_checked")
        if not lc:
            return True
        try:
            dt = datetime.fromisoformat(lc)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if (now - dt).total_seconds() > max_age:
                return True
        except Exception:
            return True
    return False


@api_router.get("/embed/{slug}")
async def get_embed(slug: str, request: Request, country: Optional[str] = Query(None)):
    m = await db.mirrors.find_one({"slug": slug})
    if not m:
        raise HTTPException(status_code=404, detail="Mirror not found")

    if country:
        geo = {"country_code": country.upper(), "country": country.upper()}
        vpn = {"blocked": False, "enabled": False}
    else:
        ip = get_client_ip(request)
        geo = await asyncio.to_thread(geolocate, ip)
        vpn = await vpn_check(ip)
    cc = geo["country_code"]

    host_ids = [l["host_id"] for l in m.get("links", [])]
    hosts = {}
    async for h in db.hosts.find({"id": {"$in": host_ids}}):
        hosts[h["id"]] = h

    # Re-verify statuses at player start so freshly-offline hosts drop to the back.
    recheck = int(os.environ.get("EMBED_RECHECK_SECONDS", "900"))
    if any(not l.get("resolved_url") for l in m.get("links", [])) or _links_stale(m.get("links", []), recheck):
        await resolve_mirror_links(m["id"])
        m = await db.mirrors.find_one({"slug": slug})

    enriched = []
    for l in m.get("links", []):
        h = hosts.get(l["host_id"])
        if not h:
            continue
        enriched.append({
            "host_id": l["host_id"],
            "host_name": h["name"],
            "host_domain": h["domain"],
            "embed_url": l.get("resolved_url") or l["embed_url"],
            "status": l.get("status", "pending"),
            "thumbnail": l.get("thumbnail"),
            "rate": rate_for_country(h, cc),
        })
    # Highest paying first; offline hosts pushed to the bottom
    enriched.sort(key=lambda x: (x["status"] == "offline", -x["rate"]))

    # record a view
    await db.mirrors.update_one({"slug": slug}, {"$inc": {"views": 1}})
    await db.views.insert_one({
        "id": str(uuid.uuid4()),
        "mirror_id": m["id"],
        "slug": slug,
        "country_code": cc,
        "country": geo["country"],
        "timestamp": now_iso(),
    })

    return {
        "title": m["title"],
        "description": m.get("description", ""),
        "slug": slug,
        "country_code": cc,
        "country": geo["country"],
        "thumbnail": next((e["thumbnail"] for e in enriched if e.get("thumbnail")), None),
        "hosts": enriched,
        "vpn_blocked": bool(vpn.get("blocked")),
        "vpn_type": vpn.get("type"),
    }

@api_router.post("/embed/{slug}/host-view/{host_id}")
async def record_host_view(slug: str, host_id: str):
    await db.views.update_one(
        {"latest_host": True, "mirror_slug": slug},
        {"$inc": {"count": 1}}, upsert=True)
    await db.host_views.update_one(
        {"slug": slug, "host_id": host_id},
        {"$inc": {"count": 1}}, upsert=True)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
@api_router.get("/stats/mirror/{mirror_id}")
async def mirror_stats(mirror_id: str, user: dict = Depends(get_current_user)):
    m = await db.mirrors.find_one({"id": mirror_id})
    if not m:
        raise HTTPException(status_code=404, detail="Mirror not found")
    if user.get("role") != "admin" and m["created_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not allowed")
    views = await db.views.find({"mirror_id": mirror_id}).to_list(10000)

    by_day = {}
    by_country = {}
    for v in views:
        day = v["timestamp"][:10]
        by_day[day] = by_day.get(day, 0) + 1
        c = v.get("country", "Unknown")
        by_country[c] = by_country.get(c, 0) + 1

    timeline = [{"date": d, "views": by_day[d]} for d in sorted(by_day.keys())]
    countries = sorted([{"country": c, "views": n} for c, n in by_country.items()],
                       key=lambda x: -x["views"])[:10]

    host_views = await db.host_views.find({"slug": m["slug"]}).to_list(100)
    hv_map = {hv["host_id"]: hv["count"] for hv in host_views}
    per_host = []
    for l in m.get("links", []):
        per_host.append({"host_name": l.get("host_name", ""), "views": hv_map.get(l["host_id"], 0)})

    return {"total_views": m.get("views", 0), "timeline": timeline,
            "countries": countries, "per_host": per_host, "links": m.get("links", [])}

@api_router.get("/stats/dashboard")
async def dashboard_stats(user: dict = Depends(get_current_user)):
    query = {} if user.get("role") == "admin" else {"created_by": user["id"]}
    mirrors = await db.mirrors.find(query).to_list(2000)
    total_views = sum(m.get("views", 0) for m in mirrors)
    online = offline = pending = 0
    offline_mirrors = 0
    for m in mirrors:
        has_offline = False
        for l in m.get("links", []):
            s = l.get("status", "pending")
            if s == "online":
                online += 1
            elif s == "offline":
                offline += 1
                has_offline = True
            else:
                pending += 1
        if has_offline:
            offline_mirrors += 1
    return {"total_mirrors": len(mirrors), "total_views": total_views,
            "links_online": online, "links_offline": offline, "links_pending": pending,
            "offline_mirrors": offline_mirrors}

@api_router.get("/admin/stats")
async def admin_stats(admin: dict = Depends(get_admin_user)):
    total_users = await db.users.count_documents({})
    total_mirrors = await db.mirrors.count_documents({})
    total_hosts = await db.hosts.count_documents({})
    mirrors = await db.mirrors.find({}).to_list(5000)
    total_views = sum(m.get("views", 0) for m in mirrors)
    offline_links = 0
    for m in mirrors:
        offline_links += sum(1 for l in m.get("links", []) if l.get("status") == "offline")
    return {"total_users": total_users, "total_mirrors": total_mirrors,
            "total_hosts": total_hosts, "total_views": total_views, "offline_links": offline_links}

@api_router.get("/admin/login-alerts")
async def login_alerts(admin: dict = Depends(get_admin_user)):
    """Suspicious IPs: many failed logins or sign-up attempts from a single IP."""
    docs = await db.login_attempts.find({}).to_list(2000)
    now = datetime.now(timezone.utc)
    alerts = []
    for d in docs:
        ident = d.get("identifier", "")
        count = int(d.get("count", 0) or 0)
        if ident.startswith("ip:"):
            kind, ip = "login", ident[3:]
        elif ident.startswith("register:"):
            kind, ip = "register", ident[len("register:"):]
        else:
            continue  # skip per-account rows to avoid noise
        if count < 3:
            continue
        locked = d.get("locked_until")
        is_locked = bool(locked and datetime.fromisoformat(locked) > now)
        # A lock only actually blocks at the enforcement threshold (login-IP: 20, sign-up: 10).
        threshold = 10 if kind == "register" else 20
        is_locked = is_locked and count >= threshold
        alerts.append({"ip": ip, "kind": kind, "count": count,
                       "locked": is_locked, "locked_until": locked})
    alerts.sort(key=lambda a: -a["count"])
    return alerts

@api_router.delete("/admin/login-alerts/{ip}")
async def clear_login_alerts(ip: str, admin: dict = Depends(get_admin_user)):
    """Unblock / clear all failed-attempt counters for one IP."""
    await db.login_attempts.delete_many(
        {"$or": [{"identifier": f"ip:{ip}"}, {"identifier": f"register:{ip}"},
                 {"identifier": {"$regex": f"^{re.escape(ip)}:"}}]})
    return {"ok": True}


class SettingsInput(BaseModel):
    site_name: str
    tagline: str = ""
    description: str = ""
    footer_text: str = ""
    ad_header: str = ""
    ad_footer: str = ""
    ad_player_top: str = ""
    ad_player_bottom: str = ""
    ad_preroll: str = ""
    ad_preroll_enabled: bool = False
    ad_preroll_seconds: int = 8
    turnstile_enabled: bool = False
    turnstile_site_key: str = ""
    turnstile_secret_key: str = ""  # blank on save = keep existing secret
    turnstile_login: bool = True
    turnstile_register: bool = True
    turnstile_gate: bool = True
    antiadblock_enabled: bool = False
    antiadblock_mode: str = "off"  # "off" | "warn" | "block"
    proxycheck_enabled: bool = False
    proxycheck_key: str = ""  # blank on save = keep existing
    opendrive_enabled: bool = False
    opendrive_user: str = ""
    opendrive_pass: str = ""  # blank on save = keep existing
    opendrive_folder: str = "MirrorStream-Backups"
    backup_schedule: str = "off"  # "off" | "daily" | "weekly"
    backup_retention: int = 7
    backup_encrypt: bool = False
    backup_password: str = ""  # blank on save = keep existing

# Fields safe to expose on the PUBLIC settings endpoint (used by the SPA everywhere).
PUBLIC_SETTINGS_KEYS = {
    "site_name", "tagline", "description", "footer_text",
    "ad_header", "ad_footer", "ad_player_top", "ad_player_bottom",
    "ad_preroll", "ad_preroll_enabled", "ad_preroll_seconds",
    "turnstile_enabled", "turnstile_site_key", "turnstile_login", "turnstile_register", "turnstile_gate",
    "antiadblock_enabled", "antiadblock_mode",
}

@api_router.get("/settings")
async def get_settings():
    """PUBLIC endpoint. Returns only non-sensitive display/config keys.
    Admin-only integration config (OpenDrive, proxycheck, backup) is NOT exposed here."""
    s = await db.settings.find_one({"key": "site"}) or {}
    s.pop("_id", None)
    merged = {**DEFAULT_SETTINGS, **s}
    return {k: merged[k] for k in PUBLIC_SETTINGS_KEYS if k in merged}

def _admin_settings_view(s: dict) -> dict:
    """Full config for the admin UI: secrets masked, replaced by has_* flags."""
    merged = {**DEFAULT_SETTINGS, **s}
    merged.pop("_id", None)
    merged["has_turnstile_secret"] = bool(merged.pop("turnstile_secret_key", None))
    merged["has_proxycheck_key"] = bool(merged.pop("proxycheck_key", None))
    merged["has_opendrive_pass"] = bool(merged.pop("opendrive_pass", None))
    merged["has_backup_password"] = bool(merged.pop("backup_password", None))
    return merged

@api_router.get("/admin/settings")
async def get_admin_settings(admin: dict = Depends(get_admin_user)):
    s = await db.settings.find_one({"key": "site"}) or {}
    return _admin_settings_view(s)

@api_router.put("/admin/settings")
async def update_settings(inp: SettingsInput, admin: dict = Depends(get_admin_user)):
    data = inp.model_dump()
    data["key"] = "site"
    # Blank secrets mean "keep the existing one" (raw secrets are never sent to the UI).
    if not data.get("turnstile_secret_key"):
        data.pop("turnstile_secret_key", None)
    if not data.get("proxycheck_key"):
        data.pop("proxycheck_key", None)
    if not data.get("opendrive_pass"):
        data.pop("opendrive_pass", None)
    if not data.get("backup_password"):
        data.pop("backup_password", None)
    await db.settings.update_one({"key": "site"}, {"$set": data}, upsert=True)
    stored = await db.settings.find_one({"key": "site"}) or {}
    return _admin_settings_view(stored)

# ---------------------------------------------------------------------------
# First-run setup wizard
# ---------------------------------------------------------------------------
class SetupInput(BaseModel):
    site_name: str
    tagline: str = ""
    description: str = ""
    footer_text: str = ""
    admin_name: str = "Administrator"
    admin_email: EmailStr
    admin_password: str = Field(min_length=6)
    token: Optional[str] = None

async def _is_installed() -> bool:
    s = await db.settings.find_one({"key": "site"})
    if s and s.get("installed"):
        return True
    return (await db.users.count_documents({"role": "admin"})) > 0

@api_router.get("/health")
async def health():
    db_ok = True
    try:
        await client.admin.command("ping")
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db": db_ok}

@api_router.get("/setup/status")
async def setup_status():
    db_connected = True
    try:
        await client.admin.command("ping")
    except Exception:
        db_connected = False
    return {"installed": await _is_installed(), "db_connected": db_connected,
            "db_name": os.environ.get("DB_NAME", ""),
            "token_required": bool(os.environ.get("SETUP_TOKEN"))}

@api_router.post("/setup/init")
async def setup_init(inp: SetupInput):
    if await _is_installed():
        raise HTTPException(status_code=403, detail="Setup has already been completed")
    setup_token = os.environ.get("SETUP_TOKEN")
    if setup_token and inp.token != setup_token:
        raise HTTPException(status_code=403, detail="Invalid setup token")
    email = inp.admin_email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    await db.users.insert_one({"email": email, "name": inp.admin_name,
                               "password_hash": hash_password(inp.admin_password),
                               "role": "admin", "created_at": now_iso()})
    settings = {"key": "site", "site_name": inp.site_name, "tagline": inp.tagline,
                "description": inp.description, "footer_text": inp.footer_text, "installed": True}
    await db.settings.update_one({"key": "site"}, {"$set": settings}, upsert=True)
    return {"ok": True}

@api_router.get("/admin/users")
async def admin_users(admin: dict = Depends(get_admin_user)):
    users = await db.users.find({}).to_list(2000)
    out = []
    for u in users:
        mirror_count = await db.mirrors.count_documents({"created_by": str(u["_id"])})
        out.append({"id": str(u["_id"]), "name": u.get("name"), "email": u["email"],
                    "role": u.get("role", "user"), "created_at": u.get("created_at"),
                    "disabled": bool(u.get("disabled")), "mirror_count": mirror_count})
    return out

@api_router.put("/admin/users/{user_id}/disabled")
async def set_user_disabled(user_id: str, inp: UserDisabledInput, admin: dict = Depends(get_admin_user)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="You cannot disable your own account")
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=404, detail="User not found")
    res = await db.users.update_one({"_id": oid}, {"$set": {"disabled": inp.disabled}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, "disabled": inp.disabled}

@api_router.post("/admin/users")
async def admin_create_user(inp: AdminCreateUserInput, admin: dict = Depends(get_admin_user)):
    if inp.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="Invalid role")
    email = inp.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    doc = {"email": email, "name": inp.name, "password_hash": hash_password(inp.password),
           "role": inp.role, "created_at": now_iso()}
    res = await db.users.insert_one(doc)
    return {"id": str(res.inserted_id), "name": inp.name, "email": email, "role": inp.role, "mirror_count": 0}

@api_router.put("/admin/users/{user_id}/password")
async def admin_set_password(user_id: str, inp: AdminPasswordInput, admin: dict = Depends(get_admin_user)):
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=404, detail="User not found")
    res = await db.users.update_one({"_id": oid}, {"$set": {"password_hash": hash_password(inp.password)}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}

@api_router.put("/admin/users/{user_id}/role")
async def set_user_role(user_id: str, inp: UserRoleInput, admin: dict = Depends(get_admin_user)):
    if inp.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="Invalid role")
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="You cannot change your own role")
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=404, detail="User not found")
    res = await db.users.update_one({"_id": oid}, {"$set": {"role": inp.role}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, "role": inp.role}

@api_router.delete("/admin/users/{user_id}")
async def delete_user(user_id: str, admin: dict = Depends(get_admin_user)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=404, detail="User not found")
    if not await db.users.find_one({"_id": oid}):
        raise HTTPException(status_code=404, detail="User not found")
    await db.mirrors.delete_many({"created_by": user_id})
    await db.users.delete_one({"_id": oid})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Seed + background jobs
# ---------------------------------------------------------------------------
DEFAULT_SETTINGS = {
    "key": "site",
    "site_name": "MirrorStream",
    "tagline": "One embed link. Every host. Maximum revenue.",
    "description": "Paste your embed links from Doodstream, VOE and other hosters. We generate a single player that always shows your viewers the best-paying source for their country.",
    "footer_text": "For legal content only.",
    "ad_header": "",
    "ad_footer": "",
    "ad_player_top": "",
    "ad_player_bottom": "",
    "ad_preroll": "",
    "ad_preroll_enabled": False,
    "ad_preroll_seconds": 8,
    "turnstile_enabled": False,
    "turnstile_site_key": "",
    "turnstile_login": True,
    "turnstile_register": True,
    "turnstile_gate": True,
    "antiadblock_enabled": False,
    "antiadblock_mode": "off",
    "proxycheck_enabled": False,
    "opendrive_enabled": False,
    "opendrive_folder": "MirrorStream-Backups",
    "backup_schedule": "off",
    "backup_retention": 7,
    "backup_encrypt": False,
}

DEFAULT_HOSTS = [
    {
        "name": "DoodStream", "domain": "doodstream.com", "default_rate": 5.0, "is_active": True,
        "api_provider": "doodstream",
        "tiers": [
            {"name": "Tier 1", "rate": 33.0, "countries": ["AU", "CA", "GB", "US"]},
            {"name": "Tier 2", "rate": 22.0, "countries": ["DK", "FI", "FR", "DE", "NO", "SE"]},
            {"name": "Tier 3", "rate": 11.0, "countries": ["AT", "IT", "JP", "NL", "ZA", "ES", "CH"]},
            {"name": "Tier 4", "rate": 7.0, "countries": ["BE", "IN", "ID", "PL", "PT", "RO", "RU", "SG", "SK"]},
            {"name": "Tier 5", "rate": 1.5, "countries": ["TR"]},
        ],
    },
    {
        "name": "VOE", "domain": "voe.sx", "default_rate": 4.0, "is_active": True,
        "api_provider": "voe",
        "tiers": [
            {"name": "Tier 1", "rate": 40.0, "countries": ["US", "CA", "GB", "AU"]},
            {"name": "Tier 2", "rate": 25.0, "countries": ["DE", "FR", "NL", "CH", "AT", "SE", "NO"]},
            {"name": "Tier 3", "rate": 12.0, "countries": ["ES", "IT", "PT", "BE", "DK", "FI"]},
            {"name": "Tier 4", "rate": 6.0, "countries": ["PL", "RO", "RU", "TR", "IN", "BR"]},
        ],
    },
]

FIRESTREAM_TIERS = [
    {"name": "Tier 1", "rate": 40.0, "countries": ["AU", "DE", "US", "GB"]},
    {"name": "Tier 2", "rate": 25.0, "countries": ["AT", "CA", "FI", "FR", "NO", "KR"]},
    {"name": "Tier 3", "rate": 15.0, "countries": ["BE", "HR", "IE", "IT", "NL", "NZ", "PL", "ES", "SE", "JP"]},
    {"name": "Tier 4", "rate": 10.0, "countries": ["AR", "BA", "BR", "BG", "CL", "CO", "CY", "EG", "GR", "HK", "HU", "ID", "MY", "MX", "PK", "PE", "RO", "RS", "TH", "AE", "VN"]},
]

# New hosters (seeded from their public earn pages; auto-refreshed daily via TIER_SCRAPERS).
NEW_HOSTS = [
    {
        "name": "Playmate", "domain": "playmate.to", "default_rate": 10.0, "is_active": True,
        "api_provider": "playmate",
        "tiers": [
            {"name": "Tier 1", "rate": 50.0, "countries": ["AU", "DE", "US", "GB"]},
            {"name": "Tier 2", "rate": 35.0, "countries": ["AT", "CA", "FI", "FR", "NO"]},
            {"name": "Tier 3", "rate": 30.0, "countries": ["BE", "HR", "IE", "IT", "NL", "NZ", "PL", "ES", "SE"]},
            {"name": "Tier 4", "rate": 15.0, "countries": ["AR", "BA", "BR", "BG", "CL", "CO", "CY", "EG", "GR", "HK", "HU", "IN", "ID", "JP", "MY", "MX", "PK", "PE", "RO", "RS", "TH", "AE", "VN"]},
        ],
    },
    {
        "name": "Vidara", "domain": "vidara.so", "default_rate": 6.0, "is_active": True,
        "api_provider": "vidara",
        "tiers": [
            {"name": "Tier 1", "rate": 40.0, "countries": ["AU", "DE", "US", "GB"]},
            {"name": "Tier 2", "rate": 25.0, "countries": ["AT", "CA", "FI", "FR", "NO"]},
            {"name": "Tier 3", "rate": 20.0, "countries": ["BE", "HR", "IE", "IT", "NL", "NZ", "PL", "ES", "SE"]},
            {"name": "Tier 4", "rate": 9.0, "countries": ["AR", "BA", "BR", "BG", "CL", "CO", "CY", "EG", "GR", "HK", "HU", "ID", "JP", "MY", "MX", "PK", "PE", "RO", "RS", "TH", "AE", "VN"]},
        ],
    },
    {
        "name": "Streamtape", "domain": "streamtape.com", "default_rate": 10.0, "is_active": True,
        "api_provider": "streamtape",
        "tiers": [],
    },
    {
        "name": "Vinovo", "domain": "vinovo.si", "default_rate": 4.5, "is_active": True,
        "api_provider": "vinovo",
        "tiers": [
            {"name": "Tier 1", "rate": 40.0, "countries": ["GB", "US", "AU", "NO", "DE"]},
            {"name": "Tier 2", "rate": 22.0, "countries": ["DK", "SE", "FI", "FR", "AT", "CA"]},
            {"name": "Tier 3", "rate": 12.0, "countries": ["NL", "CH", "IT", "BE", "IE", "NZ", "ES"]},
            {"name": "Tier 4", "rate": 7.0, "countries": ["BA", "BR", "BG", "CZ", "CY", "GR", "HK", "IN", "ID", "MX", "PL", "RO", "RU", "RS", "SK", "AE", "JP"]},
        ],
    },
    {
        "name": "VidNest", "domain": "vidnest.io", "default_rate": 5.0, "is_active": True,
        "api_provider": "vidnest",
        "tiers": [
            {"name": "Tier 1", "rate": 35.0, "countries": ["AU", "CA", "GB", "US"]},
            {"name": "Tier 2", "rate": 25.0, "countries": ["DK", "FI", "SE", "NO", "DE", "FR"]},
            {"name": "Tier 3", "rate": 15.0, "countries": ["JP", "BE", "ES", "IT", "PL", "CH", "AT", "NL", "ZA"]},
            {"name": "Tier 4", "rate": 10.0, "countries": ["RU", "SG", "ID", "SK", "PT", "RO", "HU", "UA"]},
            {"name": "Tier 5", "rate": 5.5, "countries": ["PH", "TR", "IN", "VN", "EG", "BR", "MX"]},
        ],
    },
]

async def seed():
    await db.users.create_index("email", unique=True)
    # Only auto-create an admin when explicit credentials are provided via env.
    # Otherwise the first admin is created through the /setup web wizard.
    admin_email = os.environ.get("ADMIN_EMAIL")
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if admin_email and admin_password:
        admin_email = admin_email.lower()
        existing = await db.users.find_one({"email": admin_email})
        if not existing:
            await db.users.insert_one({"email": admin_email, "name": "Administrator",
                                       "password_hash": hash_password(admin_password),
                                       "role": "admin", "created_at": now_iso()})
            logger.info("Seeded admin user")
        elif not verify_password(admin_password, existing["password_hash"]):
            await db.users.update_one({"email": admin_email},
                                      {"$set": {"password_hash": hash_password(admin_password), "role": "admin"}})
    if await db.hosts.count_documents({}) == 0:
        for h in DEFAULT_HOSTS:
            doc = dict(h)
            doc["id"] = str(uuid.uuid4())
            doc["created_at"] = now_iso()
            await db.hosts.insert_one(doc)
        logger.info("Seeded default hosts")

    if await db.settings.count_documents({"key": "site"}) == 0:
        await db.settings.insert_one(dict(DEFAULT_SETTINGS))
        logger.info("Seeded default settings")

    # Migrate existing hosts to attach api_provider by name.
    await db.hosts.update_many({"name": "DoodStream", "api_provider": {"$exists": False}},
                               {"$set": {"api_provider": "doodstream"}})
    await db.hosts.update_many({"name": "VOE", "api_provider": {"$exists": False}},
                               {"$set": {"api_provider": "voe"}})

    # Migrate API keys from .env into the DB (one-time) so admins manage them in the dashboard.
    dood_key = os.environ.get("DOODSTREAM_API_KEY")
    if dood_key:
        await db.hosts.update_many({"api_provider": "doodstream", "api_key": {"$exists": False}},
                                   {"$set": {"api_key": dood_key}})
    voe_key = os.environ.get("VOE_API_KEY")
    if voe_key:
        await db.hosts.update_many({"api_provider": "voe", "api_key": {"$exists": False}},
                                   {"$set": {"api_key": voe_key}})

    fire_key = os.environ.get("FIRESTREAM_API_KEY")
    if fire_key:
        await db.hosts.update_many({"api_provider": "firestream", "api_key": {"$in": [None, ""]}},
                                   {"$set": {"api_key": fire_key}})
    fire_email = os.environ.get("FIRESTREAM_EMAIL")
    fire_pw = os.environ.get("FIRESTREAM_PASSWORD")
    if fire_email and fire_pw:
        await db.hosts.update_many({"api_provider": "firestream", "login_password": {"$in": [None, ""]}},
                                   {"$set": {"login_email": fire_email, "login_password": fire_pw}})

    # Backfill FireStream earning tiers (only when none are set, so admin edits are preserved).
    await db.hosts.update_many({"api_provider": "firestream", "tiers": {"$in": [[], None]}},
                               {"$set": {"tiers": FIRESTREAM_TIERS, "default_rate": 5.0}})

    # Seed Firestream host if none exists yet.
    if await db.hosts.count_documents({"api_provider": "firestream"}) == 0:
        await db.hosts.insert_one({
            "id": str(uuid.uuid4()),
            "name": "FireStream",
            "domain": "firestream.to",
            "default_rate": 5.0,
            "is_active": True,
            "api_provider": "firestream",
            "api_key": os.environ.get("FIRESTREAM_API_KEY", ""),
            "tiers": FIRESTREAM_TIERS,
            "created_at": now_iso(),
        })
        logger.info("Seeded FireStream host")

    # Seed the newer hosters (one each) if they don't exist yet. Tiers are pre-filled from
    # their earn pages and auto-refreshed daily; admins add the API key to activate them.
    for nh in NEW_HOSTS:
        if await db.hosts.count_documents({"api_provider": nh["api_provider"]}) == 0:
            doc = dict(nh)
            doc["id"] = str(uuid.uuid4())
            doc["created_at"] = now_iso()
            await db.hosts.insert_one(doc)
            logger.info(f"Seeded {nh['name']} host")

    cred = ROOT_DIR.parent / "memory" / "test_credentials.md"
    try:
        cred.write_text(
            "# Test Credentials\n\n"
            f"## Admin\n- Email: {admin_email}\n- Password: {admin_password}\n- Role: admin\n\n"
            "## Auth endpoints\n- POST /api/auth/register\n- POST /api/auth/login\n"
            "- POST /api/auth/logout\n- GET /api/auth/me\n\n"
            "Register a new user via /api/auth/register for a normal 'user' role account.\n")
    except Exception as e:
        logger.warning(f"Could not write test_credentials.md: {e}")

# ---------------------------------------------------------------------------
# Backup / Restore + OpenDrive cloud upload
# ---------------------------------------------------------------------------
BACKUP_DATA_DIR = os.environ.get("BACKUP_DATA_DIR", str(ROOT_DIR / "data"))
OD_BASE = "https://dev.opendrive.com/api/v1"
BACKUP_PREFIX = "mirrorstream-backup-"

async def build_backup_zip(password: str = "") -> bytes:
    """Zip every MongoDB collection as JSON + server config files (.env) + any files
    under BACKUP_DATA_DIR (e.g. future uploads). If `password` is set, the archive is
    AES-256 encrypted (pyzipper)."""
    buf = io.BytesIO()
    manifest = {"created_at": now_iso(), "db": os.environ["DB_NAME"], "collections": {}, "config": [], "files": 0,
                "encrypted": bool(password)}
    os.makedirs(BACKUP_DATA_DIR, exist_ok=True)
    if password:
        z = pyzipper.AESZipFile(buf, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES)
        z.setpassword(password.encode("utf-8"))
    else:
        z = zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED)
    with z:
        for name in await db.list_collection_names():
            docs = await db[name].find({}).to_list(100000)
            for d in docs:
                if isinstance(d.get("_id"), ObjectId):
                    d["_id"] = str(d["_id"])
            z.writestr(f"db/{name}.json", json.dumps(docs, default=str, ensure_ascii=False))
            manifest["collections"][name] = len(docs)
        # Server configuration files (for disaster recovery / moving servers).
        for label, path in [("backend.env", ROOT_DIR / ".env"),
                            ("frontend.env", ROOT_DIR.parent / "frontend" / ".env")]:
            if os.path.isfile(path):
                z.write(str(path), f"config/{label}")
                manifest["config"].append(label)
        # Arbitrary server data files (uploads etc.) placed under BACKUP_DATA_DIR.
        if os.path.isdir(BACKUP_DATA_DIR):
            for root, _, files in os.walk(BACKUP_DATA_DIR):
                for fn in files:
                    fp = os.path.join(root, fn)
                    z.write(fp, f"files/{os.path.relpath(fp, BACKUP_DATA_DIR)}")
                    manifest["files"] += 1
        z.writestr("manifest.json", json.dumps(manifest, indent=2))
    return buf.getvalue()

async def restore_backup_zip(data: bytes, password: str = "") -> dict:
    restored = {}

    def _safe_join(base, rel):
        # Zip-Slip guard: reject entries that escape the base directory.
        base_n = os.path.normpath(base)
        dest = os.path.normpath(os.path.join(base_n, rel))
        if dest != base_n and not dest.startswith(base_n + os.sep):
            return None
        return dest

    # pyzipper reads plain ZIPs too, so use it for both encrypted and unencrypted backups.
    z = pyzipper.AESZipFile(io.BytesIO(data))
    if password:
        z.setpassword(password.encode("utf-8"))
    with z:
        is_encrypted = any((getattr(i, "flag_bits", 0) & 0x1) for i in z.infolist())
        if is_encrypted and not password:
            raise HTTPException(status_code=400, detail="This backup is encrypted. Please enter the backup password.")
        names = z.namelist()
        if "manifest.json" not in names:
            raise HTTPException(status_code=400, detail="Invalid backup file (no manifest.json)")
        try:
            z.read("manifest.json")  # validates the password early
        except RuntimeError:
            raise HTTPException(status_code=400, detail="Wrong backup password or corrupted archive.")
        for n in names:
            if n.startswith("db/") and n.endswith(".json"):
                coll = n[3:-5]
                if not coll or "/" in coll or coll.startswith("system."):
                    continue
                docs = json.loads(z.read(n) or b"[]")
                for d in docs:
                    _id = d.get("_id")
                    if isinstance(_id, str) and ObjectId.is_valid(_id):
                        d["_id"] = ObjectId(_id)
                await db[coll].delete_many({})
                if docs:
                    await db[coll].insert_many(docs)
                restored[coll] = len(docs)
            elif n.startswith("files/") and not n.endswith("/"):
                dest = _safe_join(BACKUP_DATA_DIR, n[len("files/"):])
                if not dest:
                    continue
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as f:
                    f.write(z.read(n))
            elif n.startswith("config/") and not n.endswith("/"):
                # Never overwrite the LIVE .env (would break the running server). Extract the
                # backed-up config to a review folder so the admin can apply it manually.
                dest = _safe_join(os.path.join(BACKUP_DATA_DIR, "restored-config"), n[len("config/"):])
                if not dest:
                    continue
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as f:
                    f.write(z.read(n))
                restored["_config_files"] = restored.get("_config_files", 0) + 1
    return restored

def _od_login(user: str, passwd: str) -> str:
    r = requests.post(f"{OD_BASE}/session/login.json", json={"username": user, "passwd": passwd}, timeout=30)
    r.raise_for_status()
    sid = r.json().get("SessionID")
    if not sid:
        raise RuntimeError("OpenDrive login failed (check username/password)")
    return sid

def _od_folder(sid: str, name: str) -> str:
    r = requests.get(f"{OD_BASE}/folder/list.json/{sid}/0", timeout=30)
    r.raise_for_status()
    for f in (r.json().get("Folders") or []):
        if f.get("Name") == name:
            return f["FolderID"]
    r = requests.post(f"{OD_BASE}/folder.json", json={
        "session_id": sid, "folder_name": name, "folder_sub_parent": "0",
        "folder_is_public": 0, "folder_public_upl": 0, "folder_public_display": 0, "folder_public_dnl": 0,
    }, timeout=30)
    r.raise_for_status()
    return r.json()["FolderID"]

def _od_upload(sid: str, folder_id: str, filename: str, data: bytes):
    fid = requests.post(f"{OD_BASE}/upload/create_file.json",
                        json={"session_id": sid, "folder_id": folder_id, "file_name": filename},
                        timeout=30).json()["FileId"]
    op = requests.post(f"{OD_BASE}/upload/open_file_upload.json",
                       json={"session_id": sid, "file_id": fid, "file_size": len(data)}, timeout=30).json()
    temp = op.get("TempLocation")
    chunk = 10 * 1024 * 1024
    offset = 0
    while offset < len(data):
        part = data[offset:offset + chunk]
        requests.post(f"{OD_BASE}/upload/upload_file_chunk.json",
                      data={"session_id": sid, "file_id": fid, "temp_location": temp,
                            "chunk_offset": str(offset), "chunk_size": str(len(part))},
                      files={"file_data": (filename, io.BytesIO(part), "application/octet-stream")},
                      timeout=180).raise_for_status()
        offset += len(part)
    requests.post(f"{OD_BASE}/upload/close_file_upload.json",
                  json={"session_id": sid, "file_id": fid, "file_size": len(data), "temp_location": temp},
                  timeout=30).raise_for_status()
    return fid

def opendrive_upload_and_retain(user, passwd, folder, filename, data, retention) -> dict:
    """Sync (run in a thread). Uploads the backup then trims old backups to `retention`."""
    sid = _od_login(user, passwd)
    folder_id = _od_folder(sid, folder)
    fid = _od_upload(sid, folder_id, filename, data)
    deleted = 0
    try:
        listing = requests.get(f"{OD_BASE}/folder/list.json/{sid}/{folder_id}", timeout=30).json()
        backups = [f for f in (listing.get("Files") or []) if str(f.get("Name", "")).startswith(BACKUP_PREFIX)]
        backups.sort(key=lambda f: f.get("Name", ""), reverse=True)
        for old in backups[max(1, int(retention)):]:
            oid = old.get("FileId") or old.get("FileID")
            if oid:
                requests.delete(f"{OD_BASE}/file.json/{sid}/{oid}", timeout=30)
                deleted += 1
    except Exception as e:
        logger.warning(f"OpenDrive retention cleanup failed: {type(e).__name__}")
    return {"ok": True, "file_id": fid, "size": len(data), "deleted": deleted}


@api_router.get("/admin/backup/download")
async def backup_download(admin: dict = Depends(get_admin_user)):
    s = await db.settings.find_one({"key": "site"}) or {}
    pw = s.get("backup_password", "") if s.get("backup_encrypt") else ""
    data = await build_backup_zip(pw)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    fn = f"{BACKUP_PREFIX}{ts}.zip"
    return StreamingResponse(io.BytesIO(data), media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{fn}"'})

@api_router.post("/admin/backup/run")
async def backup_run(admin: dict = Depends(get_admin_user)):
    s = await db.settings.find_one({"key": "site"}) or {}
    if not (s.get("opendrive_enabled") and s.get("opendrive_user") and s.get("opendrive_pass")):
        raise HTTPException(status_code=400, detail="OpenDrive is not configured/enabled")
    if s.get("backup_encrypt") and not s.get("backup_password"):
        raise HTTPException(status_code=400, detail="Encryption is enabled but no backup password is set.")
    pw = s.get("backup_password", "") if s.get("backup_encrypt") else ""
    data = await build_backup_zip(pw)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    fn = f"{BACKUP_PREFIX}{ts}.zip"
    try:
        res = await asyncio.to_thread(opendrive_upload_and_retain, s["opendrive_user"], s["opendrive_pass"],
                                      s.get("opendrive_folder", "MirrorStream-Backups"), fn, data,
                                      int(s.get("backup_retention", 7)))
    except Exception as e:
        logger.warning(f"backup_run upload failed: {type(e).__name__}: {e}")
        await db.settings.update_one({"key": "site"}, {"$set": {"last_backup_at": now_iso(), "last_backup_status": "error"}})
        raise HTTPException(status_code=502, detail="OpenDrive upload failed. Check the credentials.")
    await db.settings.update_one({"key": "site"}, {"$set": {"last_backup_at": now_iso(), "last_backup_status": "ok"}})
    return {"ok": True, "filename": fn, "size_bytes": res["size"], "deleted_old": res["deleted"]}

@api_router.post("/admin/backup/test-opendrive")
async def backup_test_opendrive(admin: dict = Depends(get_admin_user)):
    s = await db.settings.find_one({"key": "site"}) or {}
    if not (s.get("opendrive_user") and s.get("opendrive_pass")):
        return {"ok": False, "message": "No OpenDrive credentials stored"}
    try:
        def _t():
            sid = _od_login(s["opendrive_user"], s["opendrive_pass"])
            fid = _od_folder(sid, s.get("opendrive_folder", "MirrorStream-Backups"))
            return fid
        folder_id = await asyncio.to_thread(_t)
        return {"ok": True, "message": "Connection OK", "folder_id": folder_id}
    except Exception as e:
        logger.warning(f"opendrive test failed: {type(e).__name__}")
        return {"ok": False, "message": "Login failed. Check username/password."}

@api_router.post("/admin/backup/verify-password")
async def backup_verify_password(password: str = Form(""), admin: dict = Depends(get_admin_user)):
    """Confirms the entered password matches the stored backup password by encrypting a
    tiny test ZIP with the STORED password and decrypting it with the ENTERED one."""
    s = await db.settings.find_one({"key": "site"}) or {}
    stored = s.get("backup_password") or ""
    if not stored:
        return {"ok": False, "message": "No backup password is stored yet. Save one first."}
    if not password:
        return {"ok": False, "message": "Please enter a password to check."}

    def _check():
        buf = io.BytesIO()
        with pyzipper.AESZipFile(buf, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as z:
            z.setpassword(stored.encode("utf-8"))
            z.writestr("check.txt", b"ok")
        buf.seek(0)
        with pyzipper.AESZipFile(buf) as z:
            z.setpassword(password.encode("utf-8"))
            try:
                return z.read("check.txt") == b"ok"
            except RuntimeError:
                return False

    match = await asyncio.to_thread(_check)
    return {"ok": bool(match),
            "message": "Password matches the stored backup password." if match
                       else "Password does NOT match the stored backup password."}

@api_router.post("/admin/backup/restore")
async def backup_restore(file: UploadFile = File(...), password: str = Form(""), admin: dict = Depends(get_admin_user)):
    raw = await file.read()
    if len(raw) > 200 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Backup file too large")
    try:
        restored = await restore_backup_zip(raw, password)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Not a valid ZIP backup file")
    return {"ok": True, "restored": restored}


async def backup_scheduler():
    """Hourly wake-up; runs an OpenDrive backup when due per the admin schedule."""
    while True:
        await asyncio.sleep(3600)
        try:
            s = await db.settings.find_one({"key": "site"}) or {}
            sched = s.get("backup_schedule", "off")
            if sched not in ("daily", "weekly"):
                continue
            if not (s.get("opendrive_enabled") and s.get("opendrive_user") and s.get("opendrive_pass")):
                continue
            interval = 86400 if sched == "daily" else 604800
            last = s.get("backup_auto_at")
            now = datetime.now(timezone.utc)
            if last and (now - datetime.fromisoformat(last)).total_seconds() < interval:
                continue
            pw = s.get("backup_password", "") if s.get("backup_encrypt") else ""
            data = await build_backup_zip(pw)
            fn = f"{BACKUP_PREFIX}{now.strftime('%Y%m%d-%H%M%S')}.zip"
            res = await asyncio.to_thread(opendrive_upload_and_retain, s["opendrive_user"], s["opendrive_pass"],
                                          s.get("opendrive_folder", "MirrorStream-Backups"), fn, data,
                                          int(s.get("backup_retention", 7)))
            await db.settings.update_one({"key": "site"}, {"$set": {
                "backup_auto_at": now.isoformat(), "last_backup_at": now.isoformat(),
                "last_backup_status": "ok" if res.get("ok") else "error"}})
            logger.info(f"Scheduled backup uploaded: {fn}")
        except Exception as e:
            logger.error(f"backup_scheduler error: {e}")


async def offline_checker():
    interval = int(os.environ.get("CHECK_INTERVAL_HOURS", "6")) * 3600
    while True:
        await asyncio.sleep(interval)
        try:
            mirrors = await db.mirrors.find({}).to_list(5000)
            for m in mirrors:
                await resolve_mirror_links(m["id"])
            logger.info("Offline check completed")
        except Exception as e:
            logger.error(f"Offline checker error: {e}")

async def tier_updater():
    interval = int(os.environ.get("TIER_UPDATE_HOURS", "24")) * 3600
    while True:
        await asyncio.sleep(interval)
        try:
            hosts = await db.hosts.find({"api_provider": {"$in": list(TIER_SCRAPERS.keys())}}).to_list(100)
            for h in hosts:
                await refresh_host_tiers(h)
            logger.info("Tier auto-update completed")
        except Exception as e:
            logger.error(f"Tier updater error: {e}")

@app.on_event("startup")
async def on_startup():
    await seed()
    asyncio.create_task(offline_checker())
    asyncio.create_task(tier_updater())
    asyncio.create_task(backup_scheduler())

@app.on_event("shutdown")
async def on_shutdown():
    client.close()


@api_router.get("/")
async def root():
    return {"message": "MirrorStream API"}

app.include_router(api_router)

_cors_origins = [o.strip() for o in os.environ.get('CORS_ORIGINS', '*').split(',') if o.strip()]
_cors_wildcard = _cors_origins == ['*']
app.add_middleware(
    CORSMiddleware,
    # A wildcard origin cannot be combined with credentials (browsers reject it and it is
    # insecure). The SPA authenticates via Bearer tokens, so credentials aren't required for "*".
    allow_credentials=not _cors_wildcard,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
