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
- **Database-backed hoster API keys**: API keys moved out of `.env` into the `hosts` collection, managed in the Admin Dashboard (masked password field, "leave blank to keep" behavior). `GET /api/hosts` never returns raw keys — only `has_api_key: bool`. `.env` values remain a fallback (`resolve_api_key`). Auto-migrated DoodStream/VOE/FireStream keys on startup.
- **FireStream integration** (firestream.to): new host + `api_provider="firestream"`, online/offline + title detection via `https://firestream.to/api/file/info`. Verified online (file_code `1uuFmyaj`) and offline (bogus code) resolution end-to-end.
- **Dynamic hoster management**: Admin can add/edit any hoster (name, domain, provider, api_key, tiers) fully from the dashboard — no server files.
- **Responsive dashboard**: DashboardLayout now has a mobile top bar + slide-in drawer (fixes horizontal overflow on small screens); desktop unchanged.
- Verified: 41/41 backend tests, all desktop admin flows (iteration_10).

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
