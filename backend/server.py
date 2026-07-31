from dotenv import load_dotenv
from pathlib import Path
import os

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, Query
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

def api_resolve_link(provider: str, embed_url: str, api_key: Optional[str] = None):
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
    except Exception as e:
        logger.warning(f"api_resolve_link {provider} failed: {e}")
    return None

def validate_api_key(provider: Optional[str], key: Optional[str]) -> dict:
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
        return {"ok": False, "message": "No key validation available for this provider"}
    except Exception as e:
        return {"ok": False, "message": f"Request failed: {e}"}


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
            providers[h["id"]] = (h.get("api_provider"), resolve_api_key(h.get("api_provider"), h.get("api_key")))
        for l in links:
            prov, key = providers.get(l["host_id"], (None, None))
            api = await asyncio.to_thread(api_resolve_link, prov, l["embed_url"], key) if prov else None
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
    if not key and inp.host_id:
        h = await db.hosts.find_one({"id": inp.host_id})
        if h:
            provider = provider or h.get("api_provider")
            key = resolve_api_key(h.get("api_provider"), h.get("api_key"))
    if not key:
        key = resolve_api_key(provider, None)
    return await asyncio.to_thread(validate_api_key, provider, key)

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
    if provider not in ("doodstream", "voe", "firestream"):
        raise HTTPException(status_code=400, detail="Auto-fix is not supported for this host")
    if provider == "firestream" and not (host.get("login_email") and host.get("login_password")):
        raise HTTPException(status_code=400, detail="FireStream login not configured")
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
    else:
        ip = get_client_ip(request)
        geo = await asyncio.to_thread(geolocate, ip)
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

class SettingsInput(BaseModel):
    site_name: str
    tagline: str = ""
    description: str = ""
    footer_text: str = ""
    ad_header: str = ""
    ad_footer: str = ""
    ad_player_top: str = ""
    ad_player_bottom: str = ""
    turnstile_enabled: bool = False
    turnstile_site_key: str = ""
    turnstile_secret_key: str = ""  # blank on save = keep existing secret
    turnstile_login: bool = True
    turnstile_register: bool = True
    turnstile_gate: bool = True

@api_router.get("/settings")
async def get_settings():
    s = await db.settings.find_one({"key": "site"})
    if not s:
        return DEFAULT_SETTINGS
    s.pop("_id", None)
    merged = {**DEFAULT_SETTINGS, **s}
    # Never leak the Turnstile secret; expose only whether one is stored.
    secret = merged.pop("turnstile_secret_key", None)
    merged["has_turnstile_secret"] = bool(secret)
    return merged

@api_router.put("/admin/settings")
async def update_settings(inp: SettingsInput, admin: dict = Depends(get_admin_user)):
    data = inp.model_dump()
    data["key"] = "site"
    # Blank secret means "keep the existing one" (raw secret is never sent to the UI).
    if not data.get("turnstile_secret_key"):
        data.pop("turnstile_secret_key", None)
    await db.settings.update_one({"key": "site"}, {"$set": data}, upsert=True)
    data.pop("_id", None)
    data.pop("turnstile_secret_key", None)
    return {**data, "has_turnstile_secret": bool(
        (await db.settings.find_one({"key": "site"}) or {}).get("turnstile_secret_key"))}

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
    "turnstile_enabled": False,
    "turnstile_site_key": "",
    "turnstile_login": True,
    "turnstile_register": True,
    "turnstile_gate": True,
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
