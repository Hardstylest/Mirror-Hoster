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
- **Admin: Benutzer anlegen**: Button + Modal (`POST /api/admin/users`) legt neue Nutzer inkl. Rolle (user/admin) an; Duplikat-E-Mail → 400. Login danach direkt möglich.
- **Admin: Passwort zurücksetzen**: Button pro Nutzer (`PUT /api/admin/users/{id}/password`), setzt neues Passwort (min. 6 Zeichen, bcrypt).
- **Benutzer-Suche**: Filterfeld (Name/E-Mail) in der Benutzerliste (clientseitig).
- **Reparatur-Verlauf**: `GET /api/fix-logs` + Sektion auf der Offline-Seite; jeder erfolgreiche (auto/bulk) Fix wird in `db.fix_logs` geloggt (Mirror, Hoster, neuer Link, Zeit).
- **Mobile**: Benutzer-Tabelle horizontal scrollbar, Admin-Tab-Leiste scrollbar; load()-Fehlerbehandlung ergänzt.
- Benutzerverwaltung (Rolle/Löschen, Selbstschutz) aus vorheriger Runde.
- Verifiziert: iteration_12 – alle 4 Feature-APIs + Desktop-Flows grün (53/54 Backend; einzige Abweichung: credentialed-CORS Wildcard = bestehende Deploy-Config, App nutzt Bearer-Auth).
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

## Backlog / Next
- P1: Automatic scraping of hosters' public earn-money pages to auto-refresh tiers (currently admin-managed; scrape verified feasible for Doodstream earn page).
- P1: Bulk mirror import; embed URL auto-parsing/normalization per host.
- P2: Email verification + password reset UI; referral/earnings estimate per mirror.
- P2: Public embed theming/branding options; more seeded hosters (Streamtape, Filemoon, Vidoza).
