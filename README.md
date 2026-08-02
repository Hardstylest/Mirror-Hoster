# MirrorStream

**MirrorStream** ist eine Multi-Hoster-Video-Mirror-Plattform (ähnlich listmirror.com). Nutzer fügen Embed-Links mehrerer Streaming-Hoster (Doodstream, VOE, FireStream …) zu einem einzigen Player zusammen. Der Player zeigt Reiter-Tabs mit den Favicons der Hoster und wählt für jeden Besucher automatisch den Anbieter mit dem **höchsten Verdienst für dessen Land** (per IP-Geolocation) aus.

## Features

- **Benutzer-Registrierung & Dashboard** – eigene Mirrors anlegen, suchen, paginieren, Embed-Code generieren
- **Multi-Hoster-Player** mit Browser-artigen Tabs + Hoster-Favicons, Click-to-Play-Overlay
- **Geo-basiertes Routing** – höchstbezahlter Online-Hoster pro Land zuerst (via ip-api.com)
- **Online/Offline-Erkennung** über die offiziellen Hoster-APIs, veraltete Status werden beim Player-Start neu geprüft
- **Offline-Streams-Übersicht** mit Badge-Zähler + **Auto-Fix** (sucht per Hoster-API den neuen Link zum gleichen Dateinamen) + Bulk-Fix + Reparatur-Verlauf
- **Admin-Dashboard**: Statistiken, Hoster & Verdienst-Tiers verwalten, API-Keys/Logins pflegen, **Tier-Auto-Update** (täglich von den Earn-Seiten), Ad-Slots, Seiten-Einstellungen, **Benutzerverwaltung** (anlegen, Rolle ändern, Passwort zurücksetzen, sperren, löschen)
- **Mehrsprachig** (DE/EN), Light/Dark-Mode
- **Web-Installer** unter `/setup/install`

## Tech-Stack

- **Frontend:** React 19 (CRA), Tailwind CSS, shadcn/ui, lucide-react
- **Backend:** FastAPI (Python 3.11+), Motor (async MongoDB)
- **Datenbank:** MongoDB 5+

---

## Mindestvoraussetzungen (VPS/Server)

| Ressource | Minimum | Empfohlen |
|-----------|---------|-----------|
| CPU       | 1 vCPU  | 2 vCPU |
| RAM       | 1 GB    | 2 GB |
| Speicher  | 10 GB SSD | 20 GB SSD |
| OS        | Ubuntu 22.04 / Debian 12 | Ubuntu 22.04 LTS |

**Software:** Python 3.11+, Node.js 18/20 + Yarn, MongoDB 5+ (lokal oder MongoDB Atlas), Nginx (Reverse-Proxy + TLS via Let's Encrypt). Eine Domain, die auf die Server-IP zeigt.

> Hinweis: RAM-Bedarf steigt mit MongoDB. Für kleine Instanzen reichen 1–2 GB; bei vielen Mirrors/Views eher 2–4 GB.

---

## Installation

### 1. Pakete installieren (Ubuntu-Beispiel)

```bash
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip nginx git curl
# Node.js 20 + Yarn
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs && sudo npm i -g yarn
# MongoDB (lokal) – oder MongoDB Atlas nutzen und diesen Schritt überspringen
# siehe https://www.mongodb.com/docs/manual/installation/
```

### 2. Projekt klonen

```bash
git clone https://github.com/Hardstylest/Mirror-Hoster.git
cd Mirror-Hoster
```

### 3. Backend konfigurieren

`backend/.env` anlegen:

```env
MONGO_URL="mongodb://127.0.0.1:27017"
DB_NAME="mirrorstream"
JWT_SECRET="<lange-zufällige-zeichenkette>"
CORS_ORIGINS="https://meinedomain.de"
```

Optionale Variablen:

```env
# Wird ein Admin hier gesetzt, wird er beim Start automatisch angelegt
# und der /setup-Assistent entfällt. Leer lassen, um /setup/install zu nutzen.
# ADMIN_EMAIL="admin@meinedomain.de"
# ADMIN_PASSWORD="<passwort>"

# Hintergrund-Jobs (Stunden)
CHECK_INTERVAL_HOURS="6"     # Offline-Check-Intervall
TIER_UPDATE_HOURS="24"       # Tier-Auto-Update-Intervall
EMBED_RECHECK_SECONDS="900"  # Frische-Prüfung im Player

# Hoster-Keys sind OPTIONAL hier – sie können auch komplett im Admin-Dashboard
# gepflegt werden. Beim ersten Start werden hier gesetzte Werte in die DB migriert.
# DOODSTREAM_API_KEY="..."
# VOE_API_KEY="..."
# FIRESTREAM_API_KEY="..."
# FIRESTREAM_EMAIL="..."     # nur für FireStream-Auto-Fix (Session-Login)
# FIRESTREAM_PASSWORD="..."
```

Python-Abhängigkeiten & Start:

```bash
cd backend
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# Test: uvicorn server:app --host 0.0.0.0 --port 8001
```

Backend als Dienst (empfohlen, z. B. systemd):

```ini
# /etc/systemd/system/mirrorstream-api.service
[Unit]
Description=MirrorStream API
After=network.target mongod.service

[Service]
WorkingDirectory=/opt/mirrorstream/backend
EnvironmentFile=/opt/mirrorstream/backend/.env
ExecStart=/opt/mirrorstream/backend/venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001
Restart=always
User=www-data

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now mirrorstream-api
```

### 4. Frontend bauen

`frontend/.env`:

```env
REACT_APP_BACKEND_URL="https://meinedomain.de"
```

```bash
cd frontend
yarn install
yarn build      # erzeugt frontend/build/
```

### 5. Nginx (Reverse-Proxy + statisches Frontend)

```nginx
server {
    server_name meinedomain.de;

    # Frontend (statischer Build)
    root /opt/mirrorstream/frontend/build;
    index index.html;
    location / { try_files $uri /index.html; }

    # Backend – ALLE /api-Routen an FastAPI
    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

> Wichtig: Alle Backend-Routen liegen unter `/api`. Für die korrekte Geo-Erkennung sollten `X-Real-IP`/`X-Forwarded-For` durchgereicht werden.

TLS aktivieren:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d meinedomain.de
```

### 6. Ersteinrichtung über den Web-Installer

Rufe **`https://meinedomain.de/setup/install`** auf. Der Assistent fragt ab:

- **Seitenname, Tagline, Beschreibung, Footer-Text**
- **Admin-Konto** (Name, E-Mail, Passwort)

Er zeigt außerdem den **Datenbank-Verbindungsstatus** an. Nach Abschluss wird der Setup-Endpunkt gesperrt (erneuter Aufruf leitet zum Login um).

> **Warum werden die DB-Zugangsdaten nicht im Web-Formular abgefragt?**
> Das Backend braucht die MongoDB-Verbindung bereits beim Start, um überhaupt Daten lesen/schreiben zu können. Deshalb stehen `MONGO_URL`/`DB_NAME` in `backend/.env` (Schritt 3). Der Web-Installer übernimmt alles Übrige: Seiten-Konfiguration und den ersten Admin. Wer den Assistenten überspringen will, setzt `ADMIN_EMAIL`/`ADMIN_PASSWORD` in der `.env`.

### 7. Hoster einrichten

Nach dem Login als Admin → **Admin-Bereich → Anbieter & Sätze**:

- API-Keys pro Hoster eintragen (mit „Key testen"-Button)
- Für FireStream-Auto-Fix zusätzlich Login-E-Mail/Passwort hinterlegen
- „Tiers jetzt aktualisieren" holt die Verdienst-Sätze automatisch von den Earn-Seiten

---

## Wartung

- **Update:** `git pull`, dann `pip install -r backend/requirements.txt`, `yarn build` und Dienst neu starten.
- **Backup:** regelmäßig `mongodump` der Datenbank `DB_NAME`.
- **Hintergrund-Jobs** (Offline-Check, Tier-Update) laufen automatisch im Backend.

## Sicherheit

- `JWT_SECRET` lang & zufällig wählen und geheim halten.
- `CORS_ORIGINS` auf die eigene Domain beschränken (kein `*` im Produktivbetrieb).
- API-Keys/Passwörter werden nie im Klartext an das Frontend ausgeliefert.
