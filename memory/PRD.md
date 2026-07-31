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

## Bot-Schutz — Cloudflare Turnstile (2026-06)
- **Optionaler Bot-Check** via Cloudflare Turnstile, komplett über Admin-Dashboard → Tab „Sicherheit" konfigurierbar (Site Key, Secret Key maskiert, Master-Schalter + Toggles für Login/Registrierung/Site-Gate). Leer/aus = keinerlei Auswirkung.
- Keys liegen im `settings`-Doc (`turnstile_*`). Secret wird NIE ans Frontend zurückgegeben (`GET /api/settings` liefert nur `turnstile_site_key` + `has_turnstile_secret`). „Secret leer speichern = behalten".
- Backend: `verify_turnstile()` prüft Token per Cloudflare `siteverify` (nur wenn aktiviert+konfiguriert). Enforced in `POST /auth/login`, `POST /auth/register` und neuem `POST /api/security/verify-gate`.
- Frontend: `TurnstileWidget.jsx` (explicit render, Single-Use-Token → Remount bei Fehler), Widget in Login/Register, `SiteGate.jsx` als Vollbild-Overlay einmal / 24h (localStorage-Flag), Player-Routen `/e/`,`/embed/` ausgenommen. Admin-Tab „Sicherheit".
- Verifiziert per curl mit Cloudflare-Test-Keys: Token-Pass→200, Token-fehlt→400, Fail-Secret→400, Secret nicht geleakt, blank=keep. Frontend: Gate+Widget rendern (Screenshot), Disabled-State sauber.
- Standard: DEAKTIVIERT (leere Keys). User trägt eigene Cloudflare-Keys im Admin-Panel ein und aktiviert dann.

## Neue Hoster + Login-Warnung + Anti-Adblock (2026-06)
- **5 neue Hoster** voll integriert (Online/Offline via API, „Key testen", Auto-Fix per Namenssuche): **Playmate, Vidara, Streamtape, Vinovo, VidNest**. Backend: `api_resolve_link`/`validate_api_key`/`find_replacement` + Autofix-Allowlist erweitert; `NEW_HOSTS` geseedet. Streamtape braucht API-Login + API-Key (Login-Feld im Host-Editor).
- **Tiers**: Vidara/Vinovo/VidNest werden automatisch von den Earn-Seiten gescraped (täglicher Job, `TIER_SCRAPERS`), getestet ✓. Playmate-Earn-Tabelle ist client-rendered → nicht server-scrapebar; Playmate-Tiers sind akkurat geseedet (im Admin editierbar). Streamtape hat keine feste CPM-Tabelle → flache Default-Rate.
- **Login-Warnung** (Admin → Sicherheit): `GET/DELETE /api/admin/login-alerts` listet verdächtige IPs (Login/Registrierung) mit Fehlversuch-Zähler + „Entsperren". Lock-Status respektiert Schwellen (Konto 5, IP-Login 20, Registrierung 10).
- **Anti-Adblock** (Admin-Schalter, Player sperren): `AdblockGate.jsx` (Bait-Element-Erkennung) blockiert den Player bis Adblock aus; Setting `antiadblock_enabled`. Standard: AUS.
- **Security-Fixes aus Test**: Autofix für neue Provider erreichbar; kein API-Key-Leak in Fehlermeldungen; Mobile-Layout Security-Tab (min-w-0) ohne Overflow; Secret nie im GET /settings. Getestet iteration_13 + iteration_14 (Backend 10/10, Frontend-Fixes 100%).

## VPN/Proxy-Schutz + Anti-Adblock Abstufung (2026-06)
- **VPN/Proxy-Schutz via proxycheck.io**: `check_vpn`/`_proxycheck_sync` (v2 API, `vpn=1&risk=1`), 24h-Cache (`proxycheck_cache`), fail-open. Embed-Endpoint liefert `vpn_blocked`/`vpn_type`; Player zeigt Block-Overlay (`vpn-block`). Admin → Sicherheit: Toggle + maskiertes API-Key-Feld (blank=behalten, Key nie im GET /settings → `has_proxycheck_key`). Getestet: Tor→blocked(risk100), Google/Cloudflare→allowed, End-to-End embed vpn_blocked=true, Key nicht geleakt.
- **WICHTIG (Preview-Caveat)**: Im Emergent-Preview sieht das Backend nur die Load-Balancer-IP (35.186.245.91 → von proxycheck als VPN gemeldet). Daher `proxycheck_enabled` im Preview auf FALSE gelassen (Key ist gespeichert), sonst wäre der Preview-Player komplett gesperrt. Auf dem echten Docker+nginx-Server sieht das Backend die echte Besucher-IP → im Admin einfach den Schalter anmachen.
- **Anti-Adblock mit Abstufung**: neues Setting `antiadblock_mode` ("off"/"warn"/"block"). „warn" = schließbare Hinweis-Leiste (Video läuft), „block" = harte Sperre. Erkennung blockt erst nach **2 aufeinanderfolgenden** Treffern (weniger Fehlalarme) + **„Erneut prüfen"-Button** (In-Place, ohne Reload) + „Seite neu laden". Aktuell: `block` (aktiviert per User-Wunsch).
- proxycheck-Key des Users ist in der DB gespeichert (nicht im Code/Repo).

## Pre-Roll-Werbung im Player (2026-06)
- **Pre-Roll-Ad**: Neue Werbeanzeige, die *vor* dem Stream startet. Nach Klick auf „Play" erscheint ein Overlay im Player mit dem HTML/Script-Werbecode (`ad_preroll`), einem Countdown („Stream startet in Xs", `ad_preroll_seconds`, Standard 8, 0-60) und nach Ablauf einem „Werbung überspringen"-Button → dann lädt der Stream-iframe. Master-Toggle `ad_preroll_enabled`. Standard: AUS/leer.
- Admin → Tab „Werbung": neuer Bereich mit Aktivierungs-Schalter, Code-Feld (HTML/JS wie andere Ad-Slots) und Countdown-Sekunden-Feld.
- Backend: `SettingsInput` + `DEFAULT_SETTINGS` + `PUBLIC_SETTINGS_KEYS` um `ad_preroll`/`ad_preroll_enabled`/`ad_preroll_seconds` erweitert (öffentlich, da für Player nötig, kein Secret).
- Frontend: `VideoPlayer.jsx` mit Pre-Roll-Overlay (nutzt `AdSlot` zur Skript-Ausführung), `EmbedPlayer.jsx` reicht `preroll`-Props durch, i18n `player.adLabel/adCountdown/adSkip` + `admin.ads.preroll*`.
- Verifiziert (curl + Screenshot): PUT/GET Settings ok, Public-Endpoint liefert Keys, End-to-End im Player: Play → Werbung + Countdown → Skip-Button → Stream lädt. Test-Config danach zurückgesetzt.

## NOCH OFFEN (nächster Schritt)
- (leer)

## Backup / Restore + OpenDrive Auto-Upload (2026-06)
- **Manuelles Backup**: Admin → Tab „Backup" → „Jetzt herunterladen" erzeugt ein ZIP mit JSON-Export ALLER MongoDB-Collections + `manifest.json` + optional Server-Dateien aus `BACKUP_DATA_DIR` (Default `/app/backend/data`). Endpoint `GET /api/admin/backup/download`.
- **OpenDrive Cloud-Upload**: `POST /api/admin/backup/run` lädt das ZIP zu OpenDrive (Session-Login → Ordner finden/anlegen → create_file/open/upload_chunk/close) und wendet Retention an (älteste Backups über N löschen). `POST /api/admin/backup/test-opendrive` prüft Zugang. Zugangsdaten (User + Passwort) in DB-Settings, Passwort maskiert (nie im API-Response → `has_opendrive_pass`).
- **Automatischer Zeitplan**: `backup_scheduler()` (stündlicher Wake-up) läuft je nach `backup_schedule` täglich/wöchentlich; `backup_auto_at` verhindert Doppelläufe. Aktuell: **daily** aktiviert, Retention 7. Ordner „MirrorStream-Backups".
- **Restore**: `POST /api/admin/backup/restore` (Multipart-ZIP-Upload) → droppt & re-importiert alle Collections + stellt Dateien wieder her. UI mit Bestätigungsdialog (destruktiv). Getestet: 251 Einträge wiederhergestellt.
- **Security-Fix (aus Test)**: privater Config-Split — öffentliches `GET /api/settings` liefert NUR Anzeige-Keys (PUBLIC_SETTINGS_KEYS); OpenDrive-User/Backup-Metadaten/proxycheck nur über neues **admin-only** `GET /api/admin/settings` (auth-geschützt, 401 ohne Token). AdminDashboard lädt Formular aus `/admin/settings`.
- OpenDrive-Zugang des Users ist in der DB gespeichert (User: hardstylest@pm.me; Passwort nur in DB, nicht im Repo/Code). Getestet: iteration_15 (UI+Download+Restore), iteration_16 (konfigurierter Zustand + Verbindung OK + Public/Admin-Trennung) → 100%.

## Verschlüsselte Backups (AES-256) (2026-06)
- **Passwortgeschützte Backup-ZIPs** via `pyzipper` (AES-256, WZ_AES). Admin → Tab „Backup": Toggle „Backups mit Passwort verschlüsseln (AES-256)" + Passwortfeld (maskiert, blank=behalten → `has_backup_password`; nie im GET /admin/settings, nie im Public-Endpoint). Settings `backup_encrypt`/`backup_password`.
- Betrifft ALLE Backup-Wege: `GET /admin/backup/download`, `POST /admin/backup/run` (OpenDrive) und `backup_scheduler`. `backup_run` bricht mit 400 ab, wenn Verschlüsselung an ist aber kein Passwort gesetzt.
- **Restore**: `POST /admin/backup/restore` akzeptiert ein optionales `password`-Formfeld (UI: Passwortfeld unter dem Datei-Upload). Erkennt verschlüsselte ZIPs und liefert klare Fehler (kein PW / falsches PW → 400). Unverschlüsselte Backups funktionieren unverändert weiter.
- Verifiziert (curl/pyzipper + Screenshot): ZIP nicht ohne PW lesbar, Restore ohne PW→400, falsches PW→400, korrektes PW→200 (9 Collections), unverschlüsselter Download+Restore ok, UI rendert korrekt. Test-Passwort danach aus DB entfernt.

## Backlog / Next
- P1: Automatic scraping of hosters' public earn-money pages to auto-refresh tiers (currently admin-managed; scrape verified feasible for Doodstream earn page).
- P1: Bulk mirror import; embed URL auto-parsing/normalization per host.
- P2: Email verification + password reset UI; referral/earnings estimate per mirror.
- P2: Public embed theming/branding options; more seeded hosters (Streamtape, Filemoon, Vidoza).
