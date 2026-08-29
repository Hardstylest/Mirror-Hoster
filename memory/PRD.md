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
- **„Passwort prüfen"-Button**: `POST /admin/backup/verify-password` (Form `password`) verschlüsselt ein Test-ZIP mit dem GESPEICHERTEN Passwort und entschlüsselt es mit dem EINGEGEBENEN → bestätigt Übereinstimmung, bevor es ernst wird. UI im Verschlüsselungs-Bereich (nur wenn Passwort gespeichert), Toast grün/rot. Getestet: kein-PW-gespeichert/korrekt/falsch/leer + UI-Screenshot (grüner Erfolg-Toast).

## ListMirror-Import (2026-06)
- **Import ohne API/Export**: listmirror.com bietet keine API/Export UND die Login-Seite ist per Cloudflare Turnstile geschützt (Server-Login mit Zugangsdaten daher nicht zuverlässig möglich). Lösung: Die **öffentlichen Embed-Seiten** (`listmirror.com/embed/{id}`) enthalten die echten Host-Links (`data-url` je Anbieter) + Titel im HTML und sind serverseitig ohne Cloudflare-Block abrufbar.
- **Endpoint** `POST /api/mirrors/import` (auth): Input `{text, auto_create_hosts}`. Parst eingefügte Playlist- und/oder Embed-Links (auch bare IDs mit Auto-Erkennung), expandiert Playlists (`view_playlist&slug=` inkl. Pagination-Loop), scrapt jede Embed-Seite (ThreadPool, max 400 Embeds), mappt Host per Domain auf bestehende Hoster. Unbekannte Hoster: `auto_create_hosts=true` → als **inaktiv** angelegt (`auto_imported:true`), sonst übersprungen+gelistet. Dedup per `source_ref="listmirror:{slug}"`.
- **UI**: „Importieren"-Button im Dashboard-Header → Modal mit Textarea + „Hoster automatisch anlegen"-Toggle + Ergebnis-Zusammenfassung (imported/skipped/created hosts/unknown). i18n DE/EN.
- Verifiziert (curl + Screenshot): Playlist-Import 6 Mirrors mit korrekten Titeln+Links, VOE gegen bestehenden Hoster gematcht, 7 unbekannte Hoster inaktiv angelegt, Re-Import→6 skipped (Dedup), UI End-to-End inkl. deutscher Übersetzung. Test-Daten danach entfernt.
- **Stabile IDs (Update-2026-06)**: Der Mirror-`slug` = die ListMirror Video-ID (z.B. `HjWkmEHPew`), Kollisionsschutz per Suffix. Dadurch bleibt die ID beim Umzug identisch → in bestehenden Website-Embeds muss nur die Domain getauscht werden. Re-Import UPDATET bestehende Einträge (Match per `source_ref`): Titel + Host-URLs werden aufgefrischt, `id`/`slug`/`views` bleiben erhalten, unveränderte Links behalten ihren Online/Offline-Status. Response enthält jetzt `imported`/`updated`/`skipped_existing`. Verifiziert: Import→slug==listmirror-ID, Re-Import→updated, Player unter `/embed/{listmirror-ID}` abrufbar.
- **Host-Aliase / Multi-Domain-Hoster (2026-06)**: Hosts haben jetzt ein Feld `aliases` (weitere Domains). Import-`find_host` matcht Domain gegen `domain` + alle `aliases` → z.B. DoodStreams viele Embed-Domains (dsvplay.com, do7go.com, playmogo.com, dood.*, ds2play.com …) landen auf dem EINEN DoodStream-Hoster statt als Duplikate. 25 bekannte DoodStream-Domains geseedet (`DOODSTREAM_ALIASES`), im Admin-Host-Editor editierbar (Feld „Weitere Domains (Aliase)"). Einmalige `merge_duplicate_hosts()`-Migration (idempotent, im Seed) führt bereits angelegte auto-importierte Duplikat-Hoster in den passenden Haupt-Hoster über (Mirror-Links werden umgehängt, Duplikat gelöscht). Verifiziert: dsvplay.com-Duplikat entfernt, Mirrors zeigen auf DoodStream, Alias-Feld rendert im Editor.

## Bugfix: Falsche Offline-Erkennung bei Import (2026-06)
- **Symptom**: 6 importierte Links (3× VOE, 3× FireStream) als offline markiert, obwohl online.
- **Root Cause 1 (VOE)**: Beim Massen-Import feuerten alle Status-Prüfungen gleichzeitig → Provider-API rate-limited/timeout → API-Antwort ohne gültigen Envelope wurde in `api_resolve_link` fälschlich als „offline" berechnet (statt Fallback).
- **Root Cause 2 (FireStream)**: `encoding_status:"pending"` (bei importierten Fremd-Dateien normal) führte trotz `status:200` (Datei existiert & spielbar) zu „offline".
- **Fix** (`api_resolve_link`): (a) Envelope-Guard für alle Provider — wenn `info.status != 200` (rate-limited/ambig) → `return None` → Fallback auf `probe_url` (das 403/429 korrekt als „unknown"→online behandelt), niemals fälschlich offline. (b) Online-Bedingung gelockert auf „Datei existiert (`file status==200`)" für VOE/FireStream/Playmate/VidNest (encoding/canplay-Zwang entfernt), da spielbare Fremd-Dateien sonst falsch-offline waren.
- Verifiziert: Alle 20 importierten Mirrors neu geprüft → 60 Links online, 0 offline.

## Bugfix: Umlaute & Sonderzeichen im Import-Titel (2026-06)
- **Symptom**: Titel wie `Brian&#039;s Boys`, `Leo &amp; Lance`, Umlaute äöü fehlerhaft.
- **Root Cause**: `_lm_parse_embed` übernahm den `<title>` roh ohne HTML-Entity-Dekodierung; zudem konnte `requests` bei fehlendem Charset-Header auf ISO-8859-1 zurückfallen (Umlaut-Mojibake).
- **Fix**: `html.unescape()` auf Titel + Mirror-Labels (numerische `&#039;` und benannte `&amp;/&uuml;/&szlig;`), `_lm_get` erzwingt UTF-8 (`apparent_encoding`) wenn kein Charset im Header, Timeout 25s→15s. Bestehende DB-Titel nachträglich dekodiert; Re-Import aktualisiert sie ebenfalls.
- Verifiziert: Parse → „Brian's Boys" / „Leo & Lance" / „Grüße aus München & Köln"; DB-Titel korrekt.

## Gedrosselter Import + Bulk-Löschen + Mirror-Bereinigung (2026-06)
- **Gedrosselter Import**: Globales `RESOLVE_SEM = asyncio.Semaphore(3)` begrenzt gleichzeitige Provider-Statusprüfungen; Import-Resolves laufen als EIN Hintergrund-Batch (`resolve_many`, 0,25s Pause) statt N gleichzeitiger Tasks. Scraper `ThreadPoolExecutor` 10→4 + Jitter-Pause. Verhindert Rate-Limits/False-Offline.
- **Bulk-Löschen (Dashboard)**: Checkbox pro Mirror + „Alle auswählen (Seite)" + „Ausgewählte löschen (n)". `POST /api/mirrors/bulk-delete {ids}` (User-scoped, Admin=alle). testids: `select-{id}`, `select-all-toggle`, `bulk-delete-button`.
- **Mirror-Bereinigung (Admin → Anbieter)**: Entfernt Hoster-Links aus allen Mirrors; Mirrors mit 0 Links werden gelöscht. `POST /api/admin/mirrors/cleanup {host_id?, offline_only, preview}`. Filter: Hoster-Dropdown (oder „Alle Hoster" → nur Offline erlaubt, Guard 400) + „Nur Offline-Links" + Vorschau vor Ausführung. testids: `cleanup-panel`, `cleanup-host-select`, `cleanup-offline-toggle`, `cleanup-preview-button`, `cleanup-run-button`.
- Verifiziert (curl + Screenshot): Preview-Zahlen korrekt, Guard greift, beide UIs rendern & funktionieren. Keine destruktive Löschung auf Echtdaten ausgeführt.

## Offline-Hoster direkt entfernen (2026-06)
- Auf der **Offline-Streams-Seite** hat jeder Offline-Hoster-Link jetzt einen „Entfernen"-Button (neben „Auto-Fix"), um den toten Hoster direkt zu löschen — ohne den Mirror erst zu editieren.
- Endpoint `DELETE /api/mirrors/{mirror_id}/link/{host_id}` (User-scoped/Admin): entfernt genau diesen Host-Link; war es der letzte Link, wird der ganze Mirror gelöscht (+ views). Rückgabe `{deleted_mirror, remaining}`. testid `remove-link-{mid}-{hid}`, i18n `offline.removeLink/removeConfirm/removed/removedMirror` (DE/EN, Bestätigungsdialog).
- Verifiziert: 404 bei falschem Host, `remaining:1` nach 1. Löschung, `deleted_mirror:true` nach letzter, Wegwerf-Mirror sauber weg; UI zeigt 9 „Entfernen"-Buttons.

## Cover-Vorschau bei Mouseover (2026-06)
- Im Dashboard („Meine Mirrors") zeigt das Überfahren des Cover-Thumbnails eine vergrößerte, schwebende Vorschau (CSS `group/cover` hover, w-80, z-50, `object-contain`, Schatten). Kleines Cover bekommt beim Hover einen Marken-Ring + `cursor-zoom-in`. testid `cover-{id}`. Verifiziert per Screenshot.

## Security-Audit Fixes (2026-06)
- Audit-Ergebnis: CONDITIONAL PASS. Behoben: SEC-001 (MEDIUM) + H3/H4 (LOW). H1/H2 bewusst belassen (Admin-Werbe-HTML; Test-Creds nur intern).
- **SEC-001 (Import-Überlastung)**: Pro-Nutzer-Sperre (`_IMPORT_INFLIGHT`) + Cooldown (`IMPORT_COOLDOWN=8s`) → rascher Zweit-Import gibt 429. Body in `_run_import` ausgelagert, Wrapper hält Lock via try/finally. Batch-Resolve korrigiert: Insert- UND Update-Pfad sammeln `resolve_ids` und starten EINEN gedrosselten `resolve_many`. Verifiziert: 1. Import ok, 2. sofort → 429.
- **H3 (Dekompressionsbombe)**: `restore_backup_zip` prüft unkomprimierte Gesamtgröße gegen 1 GB → 400 bei Überschreitung. Normale Backups (~0,5 MB) passieren.
- **H4 (CORS)**: Startup-Warnung bei Wildcard `*` (in Produktion `CORS_ORIGINS` auf exakte Domain setzen). Mechanismus sicher (Wildcard ohne Credentials).

## Bugfix: Land immer USA hinter Cloudflare (Production) (2026-06)
- **Symptom**: Im Player-Header stand für ALLE Besucher „USA", unabhängig von der echten Herkunft (Prod-Domain via Cloudflare).
- **Root Cause**: `get_client_ip` parste `X-Forwarded-For` mit fester Proxy-Hop-Annahme (`TRUSTED_PROXY_COUNT`). Hinter Cloudflare + Ingress gibt es mehr Hops → interne IP → US.
- **Fix** (`server.py`): `get_client_ip` bevorzugt `CF-Connecting-IP`; `get_embed` liest das Land bevorzugt aus `CF-IPCountry` (kein externer Lookup), Geo-Lookup nur noch Fallback wenn Header fehlen/`XX`/`T1`. Doppelte Country-Map-Keys entfernt.
- Verifiziert lokal: DE→DE, US→US, XX→Fallback (CF-Connecting-IP→Germany), ohne CF normaler XFF-Lookup.
- **ACHTUNG: Nur in Preview gefixt — User muss neu deployen, damit es live wirkt.**
- P1: Automatic scraping of hosters' public earn-money pages to auto-refresh tiers (currently admin-managed; scrape verified feasible for Doodstream earn page).
- P1: Bulk mirror import; embed URL auto-parsing/normalization per host.
- P2: Email verification + password reset UI; referral/earnings estimate per mirror.
- P2: Public embed theming/branding options; more seeded hosters (Streamtape, Filemoon, Vidoza).


## Embed vs. Watch: schlanke Embed-Ansicht (2026-06)
- **Anforderung**: Beim Einbetten auf Fremdseiten (`/embed/:slug`) soll NUR der Player + Hoster-Tabs sichtbar sein — kein Titel/Cover, kein Land/Verdienst-Badge, keine Sprach-/Theme-Umschalter, kein "Bereitgestellt von …", keine Beschreibung, keine Banner-Ads. Volle Ansicht via neuer Route.
- **Umsetzung** (`App.js`, `EmbedPlayer.jsx`):
  - Neue Route `/watch/:slug` → `<EmbedPlayer full />` (volle Ansicht wie bisher).
  - `/embed/:slug` und `/e/:slug` → abgespeckt (Prop `full=false`, Default).
  - Prop `full` steuert Header, Banner-Ads (`ad_player_top`/`ad_player_bottom`), Beschreibung, Powered-by. Pre-Roll (im VideoPlayer) und AdblockGate bleiben in BEIDEN Varianten aktiv (Nutzerwunsch).
- Verifiziert per Screenshot: `/embed/` = nur Player+Tabs; `/watch/` = voll.


## Editor zeigt nun ALLE Links + iframe/Watch-Kopierbutton (2026-06)
- **Bug**: Nach ListMirror-Import waren Links, deren Hoster inaktiv/auto-importiert/gelöscht ist (z.B. Doodstream-Mirror-Domain oder vinovo.to → gelöschter Host), im Editor unsichtbar, obwohl der Player sie zeigt (Player nutzt alle Hosts, Editor filterte auf `is_active`). Diese Links konnten dadurch nicht bearbeitet/geleert werden.
- **Fix** (`MirrorForm.jsx`): Editor rendert jetzt aktive Hoster PLUS Fallback-Zeilen (`extraHosts`) für jeden Link, dessen host_id nicht aktiv ist. Inaktive/gelöschte Hoster erscheinen mit Badge "Inaktiv" bzw. "Nicht verwaltet" (Domain aus URL abgeleitet) + Hinweistext. Neue i18n-Keys: `form.inactiveHost/unmanagedHost/unknownHost/legacyHint`.
- **Embed-Modal erweitert** (`Dashboard.jsx`): zeigt jetzt Direktlink (schlank `/embed/`), Vollansicht-Link (`/watch/`) mit eigenem Kopierbutton, iframe-Code. Neue Keys: `dash.embedHint/watchLink/watchHint`.
- Verifiziert per Screenshot: Editor zeigt vinovo.to-Legacy-Link mit Badge; Modal zeigt beide Links.


## Legacy-Aufräumen + Flagge + Importer-Auto-Zuordnung (2026-06)
- **Legacy aufräumen** (`MirrorForm.jsx`): Legacy-Zeilen (inaktive/nicht verwaltete Hoster) haben jetzt ein "Zuordnen zu…"-Dropdown (auf aktiven Hoster umhängen) + Papierkorb (Link entfernen). Übernahme beim Speichern. Keys: `form.reassignTo/removeLink/linkRemoved/linkReassigned`.
- **Flagge statt Kürzel** (`EmbedPlayer.jsx`, nur Watch/full): Länderbadge zeigt Flaggen-Emoji + Klarname (via `Intl.DisplayNames`, sprachabhängig) statt "US"; Mouseover-Tooltip = Ländername. Helper `flagEmoji`/`countryName`.
- **Importer-Auto-Zuordnung** (`server.py` `_run_import`): Unbekannte Anbieter-Domains werden über das ListMirror-**Label** (Provider-Brand) dem passenden AKTIVEN Hoster zugeordnet (`find_host_by_label`), statt einen Inaktiv-Duplikat-Host zu erzeugen. Die neue Domain wird automatisch als Alias am Host gelernt (`learn_alias`, `$addToSet`), sodass künftige Domain-Matches sofort greifen. Import-Antwort enthält `learned_aliases`; Anzeige im Import-Ergebnis-Modal (`dash.import.autoAssigned`).
- Verifiziert: Backend-Test (unbekannte Domain + Label "DoodStream" → DoodStream zugeordnet, Alias gelernt, kein neuer Host); Screenshots für Legacy-Controls & Flagge.

## Länder-Analytics (Dashboard) + Alias-Verwaltung sichtbar (2026-06)
- **Länder-Analytics** (`server.py` `dashboard_stats`, `Dashboard.jsx`): `dashboard_stats` liefert jetzt `top_countries` (Aggregation der `views`-Collection, gruppiert nach `country_code`, Top 12; für Nicht-Admins auf eigene Mirrors gefiltert). Fehlende/leere Codes → "XX" (zusammengeführt via `$ifNull`+`$cond`). Neue Karte "Views nach Land" mit Flaggen-Emoji, Klarnamen (`Intl.DisplayNames`, sprachabhängig) und proportionalen Balken. XX → "Unbekannt". Keys: `dash.countries.title/empty/unknown`.
- **Alias-Verwaltung** (`AdminDashboard.jsx` Host-Karte + `server.py`): Host-Karten im Admin zeigen jetzt alle Alias-Domains (inkl. automatisch gelernter) als Chips mit Anzahl; jedes Chip hat ein X zum Entfernen. Neuer Endpoint `POST /api/hosts/{host_id}/remove-alias` (`$pull`). Keys: `admin.host.aliasesLabel/removeAlias/removeAliasConfirm/aliasRemoved`. (Aliases waren im Host-Editor bereits editierbar; jetzt auch in der Übersicht sichtbar/entfernbar.)
- Verifiziert: Screenshots (Dashboard-Länderkarte mit Flaggen, Admin DoodStream mit 25 Alias-Chips), curl (`top_countries`, remove-alias no-op).


## Aufräum-Tool + Cleanup verschoben + Titel-Duplikat-Warnung + Thumbnail-Befund (2026-06)
- **Aufräum-Tool (reassign-legacy)** (`server.py` `POST /api/admin/mirrors/reassign-legacy`, `components/AdminMirrorTools.jsx` `LegacyReassignPanel`): Vorschau+Anwenden. Für jeden Link mit inaktivem/gelöschtem Host wird die URL-Domain einem AKTIVEN Host zugeordnet – per Domain/Alias, sonst per Namens-Token (z.B. `vinovo.to`→"Vinovo"). Domain wird als Alias gelernt (`$addToSet`), Links pro Mirror dedupliziert (online bevorzugt). Report: `by_host`, `learned_aliases`, `unresolved`. Verifiziert (Vorschau): 287 vinovo.to→Vinovo, 13 streamtape.to→Streamtape, 2 myvidplay.com unresolved.
- **Mirror-Bereinigung verschoben**: Aus Admin „Anbieter & Sätze" in `components/AdminMirrorTools.jsx` (`MirrorCleanupPanel`) extrahiert und auf `OfflineStreams.jsx` gerendert, NUR für Admins (`useAuth().user.role`). Aus `AdminDashboard.jsx` entfernt (Panel-JSX + State + Handler).
- **Titel-Duplikat-Warnung** (`server.py` `GET /api/mirrors/check-title`, `MirrorForm.jsx`): Beim Erstellen (debounced) wird geprüft, ob der Titel schon existiert (eigene Mirrors; Admin=alle). Nicht-blockierende Warnbox mit Trefferliste + Watch/Embed-Links. Keys: `form.titleExists/titleExistsHint`.
- **Thumbnails via VOE (GELÖST)**: DoodStream-Cover sind tot (`doimg.net`/`dodoimg.com`). Lösung über VOE: der User lieferte das funktionierende Muster `https://voe.sx/cache/{file_code}_storyboard_L1.jpg` (HTTP 200, JPEG, 1279×719 16:9, kein Hotlink-Schutz, code-basiert – kein API-Call nötig). Umsetzung: `api_resolve_link` VOE setzt bei online dieses Cover; DoodStream setzt kein (totes) Cover mehr; einmalige Startup-Migration `migrate_voe_thumbnails()` (Flag `voe_thumb_migration_v1`) entfernt tote DoodStream-Thumbnails und ergänzt VOE-Storyboard-Cover für alle online VOE-Links. Verifiziert: 87/87 online VOE-Links haben Cover, 0 tote Thumbs; Dashboard zeigt Cover.


## Registrierung öffnen/schließen (Admin-Toggle) (2026-06)
- **Feature**: Admin kann öffentliche User-Registrierung an/aus schalten. Setting `registration_open` (Default true) im `site`-Settings-Doc; in `SettingsInput`, `DEFAULT_SETTINGS`, `PUBLIC_SETTINGS_KEYS`.
- **Backend** (`server.py`): `register`-Endpoint prüft zu Beginn `registration_open`; wenn false → HTTP 403 „Registration is currently closed." (Login unberührt). Flag über `PUT /api/admin/settings` (volles `siteForm`), öffentlich lesbar via `GET /api/settings`.
- **Frontend**: Admin-Toggle „Registrierung geöffnet" im Tab **Sicherheit** (`AdminDashboard.jsx`, `siteForm.registration_open`, `data-testid=registration-open-toggle`). `Register.jsx` zeigt bei geschlossen eine „Registrierung geschlossen"-Karte statt Formular. `Login.jsx` blendet „Erstelle eins" aus (zeigt Hinweis), `LandingPage.jsx` blendet Header-Register-Button aus + Hero-CTA → `/login`. `SettingsContext` FALLBACK `registration_open:true`. Keys: `auth.regClosedShort/regClosedTitle/regClosedBody`.
- **Integration**: integration_expert (JWT-Auth-Playbook) vor der Auth-Änderung konsultiert.
- Verifiziert: curl (403 bei geschlossen, `/settings` exponiert Flag, zurückgesetzt); Screenshots (Admin-Toggle im Sicherheit-Tab, geschlossene Register-Seite).


## Geo-Routing Fix: falsche IP hinter Doppel-Proxy (2026-06)
- **Bug (nur Production gaypower.org)**: Player (/watch & /embed) zeigte immer USA. Ursache via neuem Diagnose-Endpunkt gefunden: hinter Cloudflare + Rechenzentrums-LB fehlen `cf-ipcountry`/`cf-connecting-ip` (gestrippt), und `get_client_ip` (von rechts indexiert, TRUSTED_PROXY_COUNT=1) wählte die **LB-IP** (`35.186...` = US) statt der Besucher-IP. `X-Forwarded-For` z.B. `104.198.x, 172.69.x(CF), 35.186.x(LB)`.
- **Fix** (`server.py`): Neue Funktion `get_geo_ip(request)` NUR fürs Geo-Routing – nimmt `cf-connecting-ip`, sonst die **linkeste GLOBALE (öffentliche) IP** aus XFF (= echter Client), sonst `x-real-ip`/peer. `get_embed` nutzt sie jetzt für `geolocate` UND `vpn_check`; `cf-ipcountry` bleibt bevorzugt wenn vorhanden. `get_client_ip` (Security/Rate-Limit) unverändert (rechts-indexiert, anti-spoof).
- **Diagnose**: Neuer öffentlicher Endpunkt `GET /api/geo-check` – zeigt gesehene Header, gewählte IP, aufgelöstes Land, `behind_cloudflare`. Im Browser auf der Live-Domain aufrufbar.
- Verifiziert: Unit-Sim (`85.214.132.117, CF, LB` → DE; `cf-connecting-ip` gewinnt → DE) + `/api/geo-check` auf Preview (pickt jetzt linkeste Public-IP statt LB). ERFORDERT REDEPLOY für Production.


## Edit-Button auf /watch (nur Berechtigte) (2026-06)
- **Feature**: Auf der /watch-Vollansicht erscheint ein "Bearbeiten"-Button im Header, der zu `/dashboard/edit/{id}` fuehrt. So kann man beim Ansehen eigener Mirrors offline Streams (Host-Tabs zeigen Online/Offline via WLAN-Icon) direkt im Editor loeschen/ersetzen.
- **Backend** (`server.py`): Neuer Helper `get_optional_user(request)` (Auth ohne 401). `get_embed` liefert jetzt `id` und `can_edit` (True nur fuer Admin oder Mirror-Eigentuemer `created_by`).
- **Frontend** (`EmbedPlayer.jsx`): Button nur bei `data.can_edit` (full-Mode). Keys: `player.edit`.
- Verifiziert: curl (anon can_edit=False, admin can_edit=True) + Screenshot (Button sichtbar). ERFORDERT REDEPLOY fuer Production.

## Embed-Player Scrollbalken-Fix (iframe fuellt) (2026-06)
- **Bug (Production, im iframe auf Fremdseite)**: /embed hatte rechts einen Scrollbalken. Ursache: Slim-Embed nutzte `min-h-screen`+`p-4` und der Player erzwang festes 16:9 (`aspect-video`) -> Inhalt hoeher als iframe -> Overflow. ListMirror laesst den Player die iframe-Hoehe fuellen.
- **Fix**: `VideoPlayer` bekam `fill`-Prop: bei fill root=`h-full flex flex-col`, Tab-Bar `shrink-0`, Player-Frame `flex-1 min-h-0` statt `aspect-video`. `EmbedPlayer` slim-Mode: Container `h-screen w-full overflow-hidden` ohne Padding/Centering, inner `w-full h-full`, `fill={!full}`; Effekt setzt html/body height100
## Embed Auto-Hoehe + Offline-Label im Player (2026-06)
- **Auto-Hoehe (Embed)**: EmbedPlayer (slim) postet per window.parent.postMessage({type:"gaypower-embed-height", slug, height}) die ideale Hoehe (Tab-Bar + 16:9) an die Elternseite (on load, +400ms, on resize). Dashboard-Embed-Modal bietet neuen "Responsive-Embed (Auto-Hoehe)"-Codeblock: iframe mit id + kleines <script>, das die Hoehe automatisch setzt (kein Scrollbalken, keine feste Hoehe noetig). Keys: dash.responsiveCode/responsiveHint/copyResponsive. Verifiziert: Wrapper-iframe skaliert sich selbst, kein Scroll.
- **Offline-Label**: VideoPlayer Host-Tabs zeigen bei status=offline jetzt ein rotes "OFFLINE"-Badge (statt nur WifiOff-Icon); online weiterhin gruenes Wifi-Icon. Tab-Bar hat data-testid=player-tabbar (fuer Auto-Hoehe-Messung). Key: player.offlineTag. Verifiziert per Screenshot (DoodStream-Tab rot OFFLINE).
- ERFORDERT REDEPLOY fuer Production.

## Favicon + Browser-Tab-Titel (2026-06)
- **Feature**: Statt "Emergent | Fullstack App" jetzt eigenes Favicon + Titel. Generiertes Icon (cyan Mirror/Play) in public/ als favicon.ico, favicon.png(512), favicon-32.png, apple-touch-icon.png(180), logo192/512.png. index.html: <title>NurGay Mirror Stream</title>, favicon-Links, description/theme-color aktualisiert. Titel zusaetzlich dynamisch: SettingsContext setzt document.title = settings.site_name (matcht den im Admin konfigurierten Namen).
- Verifiziert: alle Icon-URLs 200; Header zeigt Brand. ERFORDERT REDEPLOY fuer Production.

## Playmate Tier-Scraper + Startup-Auto-Refresh (2026-06)
- **Bug**: Playmate-Saetze waren veraltet (50/35/30, default 10) und aktualisierten sich nie (kein Scraper; API-Key ist NUR fuer Link-Resolution, nicht fuer Tiers).
- **Fix**: `scrape_playmate_tiers()` nutzt die JSON-API `https://playmate.to/api/earn` (countries[{code,tier,per10k}], other{per10k}); Einheit $/10k (wie VOE). In TIER_SCRAPERS registriert. Live-Werte jetzt: T1=45 T2=27 T3=22 T4=12, default 8.
- **Startup-Refresh**: `tier_updater()` aktualisiert jetzt sofort beim Start (sleep ans Ende verschoben) statt erst nach 24h -> nach Redeploy sind alle Saetze direkt aktuell. Manueller Button "Saetze aktualisieren" (POST /admin/hosts/refresh-tiers) bleibt.
- Alle Scraper geprueft (ok): doodstream, voe, firestream, playmate, vidara, vinovo, vidnest. Streamtape + legacy Hosts ohne api_provider = manuell.
- ERFORDERT REDEPLOY fuer Production.

## Duplikate-Cleanup + Saetze-History + Bulk-URL-Import (2026-06)
- **Duplikate aufräumen** (POST /admin/hosts/cleanup-duplicates, preview/apply): inaktive Duplikat-Hoster deren Name zu aktivem Hoster passt -> Links umhaengen + Domain/Aliase als Alias lernen + Duplikat loeschen; ohne Treffer & 0 Links -> loeschen; mit Links & kein Ziel -> behalten+melden. UI: Button+Vorschau-Panel im Admin-Tab "Anbieter & Saetze". Verifiziert: dooodster/myvidplay->DoodStream(2/54), streamtape.to->Streamtape, del Vidoza/Mixdrop/Bigwarp, keep Veev(1).
- **Saetze-History**: refresh_host_tiers schreibt bei Aenderung in Collection tier_history {host_id,at,changes:[{tier,old,new}]}. GET /hosts/{id}/tier-history. UI: Uhr-Icon je Hoster-Karte klappt Verlauf auf (nur Scraper-Provider). Keys admin.host.history*.
- **Bulk-URL-Import (Mirror erstellen/bearbeiten)**: Feld "Mehrere URLs einfuegen" + POST /mirrors/match-urls (Domain/Alias, sonst Namens-Token) fuellt automatisch die passenden Hoster-Felder; nicht zuordenbare werden als Toast gemeldet. Keys form.bulk*. Verifiziert per Screenshot.
- Helper _match_host_for_domain/_norm_name im Backend. ERFORDERT REDEPLOY.
- HINWEIS: Turnstile in PREVIEW-DB temporaer deaktiviert (Site-Gate-Widget laedt auf Preview-Domain nicht/Prod-Key). Production-Settings unberuehrt (separate DB).


## Statistik-Bereich (neue Navi + gebündelte Auswertungen) (2026-06)
- **Neuer Menüpunkt "Statistik"** links in der Navi (`DashboardLayout.jsx`, testid `nav-statistics`), führt auf neue Route `/dashboard/statistics` (`App.js` → `pages/Statistics.jsx`).
- **Backend** `GET /api/stats/overview?period=today|7d|30d|all` (`server.py`, `_period_start_iso` + `_CC_EXPR`): liefert `total_views`, `total_earnings` (ROUGH-Schätzung), `top_countries`, `top_mirrors` (nach Views), `top_earning` (geschätzter Verdienst), `timeline` (Views/Tag), `top_hosts` (nach host_views). User-scoped (eigene Mirrors), Admin sieht alles. WICHTIG: `vmatch` schließt Tracker-Docs aus (`latest_host!=true` + `mirror_id` muss existieren), sonst KeyError bei Aggregation.
- **Verdienst-Schätzung**: pro View (mirror_id, country_code) den höchsten Satz des besten ONLINE-Hosters für das Land (rate_for_country) / 1000. Bewusst grob (Hoster-Sätze haben unterschiedliche Einheiten $/1000 vs $/10k) — im UI klar als "ca./geschätzt" markiert (`statsov.estimateNote`).
- **Zeitraum-Filter** (Heute / 7 Tage / 30 Tage / Gesamt) als Umschalter oben rechts (testid `stats-period-toggle`, `period-*`). Hinweis: `top_hosts` ist immer gesamt (host_views hat keinen Timestamp) — im UI vermerkt (`statsov.hostsNote`).
- **Panels** (testids): `panel-timeline` (Recharts LineChart), `panel-top-mirrors`, `panel-top-earning`, `panel-countries`, `panel-top-hosts`. Top-Mirror/Verdienst-Einträge verlinken auf `/dashboard/stats/{id}`.
- **"Views nach Land" aus dem Dashboard entfernt** und in die Statistik-Seite verschoben (CountryAnalytics-Komponente + Helfer aus `Dashboard.jsx` gelöscht). i18n `statsov.*` + `nav.statistics` (DE/EN).
- Verifiziert: Backend curl alle 4 Zeiträume (all: 52 Views, ~$2.2; today: 0), Frontend-Screenshot (alle Panels rendern, Nav aktiv, Zeitraum-Toggle da). ERFORDERT REDEPLOY für Production.
