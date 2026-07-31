# MirrorStream — PRD

## Original Problem Statement
Build a website like listmirror.com. Users paste embed links from streaming hosters (Doodstream, VOE.sx, …) and get a single player embed link with browser-style tabs (one per host, with favicons). Before a viewer watches, the system shows the host with the HIGHEST payout for the viewer's country first (IP geolocation). Needed: user registration, user dashboard, admin dashboard, per-movie statistics (views), offline detection of host links. Accent color #48C7F2. Auth: Email/Password.

## Architecture
- Backend: FastAPI + MongoDB (motor). JWT (Bearer + cookie) auth via bcrypt. Routes prefixed `/api`.
- Frontend: React 19 + React Router + Tailwind. Dark cinematic theme, cyan #48C7F2 accent. Fonts: Cabinet Grotesk / IBM Plex Sans / JetBrains Mono. Recharts for stats.
- IP geolocation via free ip-api.com. Offline detection via HTTP checks (manual button + background scheduler every CHECK_INTERVAL_HOURS).

## User Personas
- Uploader/Webmaster: creates mirrors, tracks views & host uptime, maximizes revenue.
- Admin: manages hosts + per-country earning tiers, views global stats and users.
- Viewer (public): watches via /e/<slug>, auto-served the best-paying host for their country.

## Core Requirements (static)
- Multi-host embed player with browser-style favicon tabs.
- Geo-based host ordering by highest payout (per-country tiers).
- Auth (register/login), user dashboard, admin dashboard.
- Per-movie statistics (views over time, countries, per-host).
- Offline detection with dashboard status badges.

## Implemented (2026-07-31)
- **Web-Installer** unter `/setup` und `/setup/install`: `GET /api/setup/status` (installed + DB-Status), `POST /api/setup/init` (Seitenname/Tagline/Beschreibung/Footer + ersten Admin anlegen, danach gesperrt). Guard leitet bei bereits installierter Instanz auf `/login`.
- **Admin-Auto-Seed optional**: Admin wird beim Start nur noch erstellt, wenn `ADMIN_EMAIL`+`ADMIN_PASSWORD` in `.env` gesetzt sind — sonst übernimmt der `/setup`-Assistent den ersten Admin.
- **README.md**: vollständige Projektbeschreibung, VPS-Mindestvoraussetzungen, Schritt-für-Schritt-Installation (MongoDB, backend/.env inkl. JWT_SECRET/CORS, systemd, Nginx+TLS), Web-Installer-Anleitung, Hoster-Einrichtung.
- Hinweis: DB-Zugangsdaten bleiben in `backend/.env` (Backend braucht sie beim Boot); der Web-Installer deckt Seiten-Config + Admin ab.
- Verifiziert: setup/status=installed, setup/init→403 bei installiert, `/setup/install`→Login-Redirect (Screenshot), Admin-Login weiterhin ok.
- **Fix-Verlauf inkl. Fehlversuche**: `db.fix_logs` speichert jetzt `status` (success/failed) + `reason`; fehlgeschlagene Auto-/Bulk-Fixes werden rot mit Grund angezeigt, erfolgreiche grün mit neuem Link.
- Admin: Benutzer anlegen, Passwort zurücksetzen, Suche, Reparatur-Verlauf (vorherige Runde).
- Verifiziert: disable→Login 403 + Selbstschutz 400 + Failed-Log per curl, UI per Screenshot.
- **"Key testen"-Button**: `POST /api/hosts/test-key` (Admin) validiert einen Hoster-API-Key gegen den Account-Endpunkt (Doodstream/FireStream `account/info`, VOE `settings/domain`). Button im Host-Editor testet getippten oder gespeicherten Key; Ergebnis als Toast (inkl. E-Mail/Balance). Key wird nie im Klartext zurückgegeben.
- **Database-backed hoster API keys**: Keys aus `.env` in `hosts`-Collection, im Admin-Dashboard editierbar (maskiert, "leer lassen = behalten"). `GET /api/hosts` liefert nur `has_api_key`. `.env` bleibt Fallback.
- **FireStream integriert** (firestream.to): Host + `api_provider="firestream"`, Online/Offline + Titel via `file/info`.
- **Dynamische Hoster-Verwaltung** und **responsives Dashboard** (mobiler Drawer).
- Verifiziert: 41/41 Backend-Tests (iteration_10), Key-Test & Embed-Sortierung per curl+Screenshot.

## Implemented (2026-07-04)
- JWT email/password auth + admin seeding (admin@mirrorstream.com / Admin@1234).
- Hosts CRUD with country earning tiers (seeded: DoodStream & VOE with real tier data).
- Mirrors CRUD, slug-based public embed, view tracking, per-host view tracking.
- Geo routing in GET /api/embed/{slug} (sorts by online + highest rate for country; ?country=XX override for testing).
- User dashboard (stat cards, mirror list, copy link, open player, check-now, edit, delete).
- Mirror statistics page (Recharts: timeline, top countries, per-host).
- Admin panel (Overview / Hosts & Rates editor with tiers / Users).
- Offline detection: manual POST /api/mirrors/{id}/check + background scheduler.
- Verified: 18/18 backend tests, all critical frontend flows.

## Security Hardening (2026-06) — Deployment- + Angriffsschutz-Check
- **SSRF-Schutz**: `probe_url` löst jetzt den Ziel-Host auf und blockt private/loopback/link-local/reserved IPs (inkl. Cloud-Metadata 169.254.169.254). Redirects werden manuell + hop-weise re-validiert (kein Redirect-basiertes SSRF). Verifiziert per Unit-Test.
- **Brute-Force härter**: zusätzlich zum per-Konto-Lockout (5/15min) gibt es jetzt einen per-IP-Lockout über alle Konten (20/15min) gegen Password-Spraying. Register per-IP gedrosselt (10/60min). Verifiziert: 401×5 → 429.
- **X-Forwarded-For Anti-Spoofing**: `get_client_ip` nimmt den vom eigenen Proxy angehängten Eintrag (rechts, `TRUSTED_PROXY_COUNT`, Default 1) statt des spoofbaren linken Werts → Rate-Limit lässt sich nicht per Header umgehen.
- **Cookies**: `COOKIE_SECURE` env (Default true) → Secure-Flag in Prod (HTTPS); nur für lokales HTTP-Dev auf false setzen.
- **CORS-Fix**: Wildcard-Origin `*` wird nicht mehr mit `allow_credentials=True` kombiniert (ungültig/unsicher); SPA nutzt Bearer-Token. Für Prod echte Domain in `CORS_ORIGINS` setzen.
- **nginx Security-Header**: X-Content-Type-Options, Referrer-Policy, X-XSS-Protection, Permissions-Policy, `server_tokens off`. Kein Frame-Deny (Player ist absichtlich einbettbar).
- **Secrets**: `backend/.env` ist korrekt gitignored und NICHT in der Git-History → JWT_SECRET + Hoster-Zugangsdaten sind nicht im Repo. `.env.example` mit Härtungs-Hinweisen (JWT_SECRET via `openssl rand -hex 32`, SETUP_TOKEN empfohlen). docker-compose reicht COOKIE_SECURE/TRUSTED_PROXY_COUNT durch.
- **Offene Entscheidung (User)**: Emergent-Plattform-Deploy verlangt getrackte `.env`; das widerspricht dem Security-Ziel (Secrets nicht committen). Für GitHub/Self-Host: `.env` gitignored lassen + Secrets rotieren. Nur wenn ausschließlich über Emergent deployt wird, .env tracken.

## Backlog / Next
- P1: Automatic scraping of hosters' public earn-money pages to auto-refresh tiers (currently admin-managed; scrape verified feasible for Doodstream earn page).
- P1: Bulk mirror import; embed URL auto-parsing/normalization per host.
- P2: Email verification + password reset UI; referral/earnings estimate per mirror.
- P2: Public embed theming/branding options; more seeded hosters (Streamtape, Filemoon, Vidoza).
