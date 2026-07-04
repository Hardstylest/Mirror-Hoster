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
import jwt
import bcrypt
import requests
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

def set_auth_cookie(response: Response, token: str):
    response.set_cookie(key="access_token", value=token, httponly=True,
                        secure=False, samesite="lax", max_age=604800, path="/")

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

class LoginInput(BaseModel):
    email: EmailStr
    password: str

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

class HostLinkInput(BaseModel):
    host_id: str
    embed_url: str

class MirrorInput(BaseModel):
    title: str
    description: Optional[str] = ""
    links: List[HostLinkInput] = []


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def get_client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"

def geolocate(ip: str) -> dict:
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}?fields=status,countryCode,country", timeout=5)
        data = r.json()
        if data.get("status") == "success":
            return {"country_code": data.get("countryCode", "XX"), "country": data.get("country", "Unknown")}
    except Exception as e:
        logger.warning(f"Geolocation failed for {ip}: {e}")
    return {"country_code": "XX", "country": "Unknown"}

def rate_for_country(host: dict, country_code: str) -> float:
    for tier in host.get("tiers", []):
        if country_code in tier.get("countries", []):
            return float(tier["rate"])
    return float(host.get("default_rate", 0))

def check_url_status(url: str) -> str:
    """Returns 'online', 'offline', or 'unknown'.
    Video hosts (Doodstream/VOE) sit behind Cloudflare/DDoS-Guard and return 403
    challenge pages to bots even when the video is live. We must NOT treat those as
    offline. Only definitive signals (404/410 or explicit not-found text) mean offline.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        r = requests.get(url, timeout=10, headers=headers, allow_redirects=True)
        code = r.status_code
        if code in (404, 410):
            return "offline"
        body = r.text.lower()[:40000]
        challenge = ["just a moment", "ddos-guard", "checking your browser",
                     "cf-browser-verification", "attention required", "enable javascript and cookies"]
        if any(x in body for x in challenge):
            return "unknown"
        if code == 200:
            not_found = ["file you are looking for", "file not found", "video not found",
                         "video has been deleted", "file has been removed", "no longer available",
                         "this video is unavailable", "404 not found", "file was deleted",
                         "video is unavailable"]
            if any(m in body for m in not_found):
                return "offline"
            return "online"
        # 403/429/503/5xx and anything else -> can't determine (assume protected/live)
        return "unknown"
    except Exception:
        return "unknown"

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
        item["host_name"] = h["name"]
        item["host_domain"] = h["domain"]
        out.append(item)
    return out

def public_mirror(doc: dict) -> dict:
    doc = dict(doc)
    doc.pop("_id", None)
    return doc


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------
@api_router.post("/auth/register")
async def register(inp: RegisterInput, response: Response):
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
    email = inp.email.lower()
    ident = f"{get_client_ip(request)}:{email}"
    attempt = await db.login_attempts.find_one({"identifier": ident})
    if attempt and attempt.get("count", 0) >= 5:
        locked_until = attempt.get("locked_until")
        if locked_until and datetime.fromisoformat(locked_until) > datetime.now(timezone.utc):
            raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(inp.password, user["password_hash"]):
        await db.login_attempts.update_one(
            {"identifier": ident},
            {"$inc": {"count": 1},
             "$set": {"locked_until": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()}},
            upsert=True)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    await db.login_attempts.delete_one({"identifier": ident})
    uid = str(user["_id"])
    token = create_access_token(uid, email)
    set_auth_cookie(response, token)
    return {"access_token": token,
            "user": {"id": uid, "email": email, "name": user.get("name"), "role": user.get("role", "user")}}

@api_router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"message": "Logged out"}

@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user


# ---------------------------------------------------------------------------
# Host endpoints
# ---------------------------------------------------------------------------
@api_router.get("/hosts")
async def list_hosts(user: dict = Depends(get_current_user)):
    hosts = await db.hosts.find({}).to_list(500)
    return [public_mirror(h) for h in hosts]

@api_router.post("/hosts")
async def create_host(inp: HostInput, admin: dict = Depends(get_admin_user)):
    doc = inp.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = now_iso()
    await db.hosts.insert_one(doc)
    return public_mirror(doc)

@api_router.put("/hosts/{host_id}")
async def update_host(host_id: str, inp: HostInput, admin: dict = Depends(get_admin_user)):
    existing = await db.hosts.find_one({"id": host_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Host not found")
    await db.hosts.update_one({"id": host_id}, {"$set": inp.model_dump()})
    updated = await db.hosts.find_one({"id": host_id})
    return public_mirror(updated)

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
        l["status"] = prev["status"] if prev and prev.get("embed_url") == l["embed_url"] else "pending"
        l["last_checked"] = prev["last_checked"] if prev else None
    await db.mirrors.update_one({"id": mirror_id},
                                {"$set": {"title": inp.title, "description": inp.description or "", "links": links}})
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
    links = m.get("links", [])
    for l in links:
        result = await asyncio.to_thread(check_url_status, l["embed_url"])
        l["status"] = "online" if result == "unknown" else result
        l["last_checked"] = now_iso()
    await db.mirrors.update_one({"id": mirror_id}, {"$set": {"links": links}})
    updated = await db.mirrors.find_one({"id": mirror_id})
    return public_mirror(updated)


# ---------------------------------------------------------------------------
# Public embed endpoint
# ---------------------------------------------------------------------------
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

    enriched = []
    for l in m.get("links", []):
        h = hosts.get(l["host_id"])
        if not h:
            continue
        enriched.append({
            "host_id": l["host_id"],
            "host_name": h["name"],
            "host_domain": h["domain"],
            "embed_url": l["embed_url"],
            "status": l.get("status", "pending"),
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
    for m in mirrors:
        for l in m.get("links", []):
            s = l.get("status", "pending")
            if s == "online":
                online += 1
            elif s == "offline":
                offline += 1
            else:
                pending += 1
    return {"total_mirrors": len(mirrors), "total_views": total_views,
            "links_online": online, "links_offline": offline, "links_pending": pending}

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

@api_router.get("/settings")
async def get_settings():
    s = await db.settings.find_one({"key": "site"})
    if not s:
        return DEFAULT_SETTINGS
    s.pop("_id", None)
    return s

@api_router.put("/admin/settings")
async def update_settings(inp: SettingsInput, admin: dict = Depends(get_admin_user)):
    data = inp.model_dump()
    data["key"] = "site"
    await db.settings.update_one({"key": "site"}, {"$set": data}, upsert=True)
    data.pop("_id", None)
    return data

@api_router.get("/admin/users")
async def admin_users(admin: dict = Depends(get_admin_user)):
    users = await db.users.find({}).to_list(2000)
    out = []
    for u in users:
        mirror_count = await db.mirrors.count_documents({"created_by": str(u["_id"])})
        out.append({"id": str(u["_id"]), "name": u.get("name"), "email": u["email"],
                    "role": u.get("role", "user"), "created_at": u.get("created_at"),
                    "mirror_count": mirror_count})
    return out


# ---------------------------------------------------------------------------
# Seed + background jobs
# ---------------------------------------------------------------------------
DEFAULT_SETTINGS = {
    "key": "site",
    "site_name": "MirrorStream",
    "tagline": "One embed link. Every host. Maximum revenue.",
    "description": "Paste your embed links from Doodstream, VOE and other hosters. We generate a single player that always shows your viewers the best-paying source for their country.",
    "footer_text": "For legal content only.",
}

DEFAULT_HOSTS = [
    {
        "name": "DoodStream", "domain": "doodstream.com", "default_rate": 5.0, "is_active": True,
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
        "tiers": [
            {"name": "Tier 1", "rate": 40.0, "countries": ["US", "CA", "GB", "AU"]},
            {"name": "Tier 2", "rate": 25.0, "countries": ["DE", "FR", "NL", "CH", "AT", "SE", "NO"]},
            {"name": "Tier 3", "rate": 12.0, "countries": ["ES", "IT", "PT", "BE", "DK", "FI"]},
            {"name": "Tier 4", "rate": 6.0, "countries": ["PL", "RO", "RU", "TR", "IN", "BR"]},
        ],
    },
]

async def seed():
    await db.users.create_index("email", unique=True)
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
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
                links = m.get("links", [])
                changed = False
                for l in links:
                    result = await asyncio.to_thread(check_url_status, l["embed_url"])
                    l["status"] = "online" if result == "unknown" else result
                    l["last_checked"] = now_iso()
                    changed = True
                if changed:
                    await db.mirrors.update_one({"id": m["id"]}, {"$set": {"links": links}})
            logger.info("Offline check completed")
        except Exception as e:
            logger.error(f"Offline checker error: {e}")

@app.on_event("startup")
async def on_startup():
    await seed()
    asyncio.create_task(offline_checker())

@app.on_event("shutdown")
async def on_shutdown():
    client.close()


@api_router.get("/")
async def root():
    return {"message": "MirrorStream API"}

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
