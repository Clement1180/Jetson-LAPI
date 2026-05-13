# LAPI - Lecture Automatique de Plaques d'Immatriculation

## Vue d'ensemble

Dispositif B2B de contrôle d'accès parking par reconnaissance de plaques. Architecture hybride Edge (Jetson) + Cloud (SaaS web).

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  CLOUD (SaaS)                                                   │
│  FastAPI + Jinja2 + SQLAlchemy                                  │
│  Multi-tenant: Admin → Tenants → Parkings → Devices → Whitelist │
│  Publie sur MQTT: lapi/{device_id}/whitelist/{add|remove|sync}  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ MQTT (sortant uniquement)
┌──────────────────────────▼──────────────────────────────────────┐
│  EDGE (Jetson)                                                   │
│  Mosquitto local (127.0.0.1) + bridge sortant vers cloud         │
│  Pipeline: YOLO voiture → YOLO-pose plaque → OCR PP-OCRv4       │
│  Tracking Kalman → Validation regex+vote → SQLite → GPIO relais │
└──────────────────────────────────────────────────────────────────┘
```

## Structure du projet

```
python/                    # Code edge (embarqué Jetson)
  main.py                  # Script test batch (fichier → fichier)
  service.py               # Point d'entrée PRODUCTION (boucle temps réel)
  src/
    core.py                # Inférence ONNX (YOLO + OCR)
    pipeline.py            # Tracking Kalman + association
    filters.py             # Filtres Kalman 8D/4D
    datastruct.py          # Structures immutables (frozen dataclasses)
    geometry.py            # Warp perspectif plaque (4 keypoints)
    viz.py                 # Visualisation debug
    loaders.py             # Lecture vidéo/image
    validation.py          # Regex plaque FR + vote multi-trames
    database.py            # SQLite whitelist (cache mémoire, lookup <1µs)
    gpio.py                # Relais GPIO Jetson (pulse + cooldown)
    mqtt_client.py         # Subscriber MQTT (whitelist + OTA + accès distant)
    camera.py              # Capture temps réel (GStreamer CSI/V4L2/USB)
    watchdog.py            # Monitoring mémoire + heartbeat
    ota_handler.py         # Mise à jour OTA (download, SHA256, backup, rollback)

web/                       # Plateforme web SaaS
  run.py                   # Entry point (uvicorn)
  app/
    main.py                # FastAPI app + lifespan
    config.py              # Settings (env vars, OTA_STORAGE_DIR, WEB_BASE_URL)
    database.py            # SQLAlchemy + SQLite/PostgreSQL
    models.py              # ORM: Admin, Tenant, TenantUser, Parking, Device, WhitelistEntry
    auth.py                # JWT cookies + hash password
    mqtt_publisher.py      # Publie vers les devices via MQTT (whitelist + OTA + accès)
    routers/
      auth_routes.py       # Login/logout
      admin.py             # CRUD tenants/users/parkings/devices + OTA upload/push
      dashboard.py         # Gestion whitelist avec owner_name + QR TOTP
      access.py            # Page publique accès QR code (plaque + nom + TOTP optionnel)
    templates/
      login.html           # Page de connexion
      base.html            # Layout de base
      admin/
        tenants.html        # Liste des clients
        tenant_detail.html  # Détail client (users, parkings, devices, OTA)
        ota.html            # Upload et liste des packages OTA
      dashboard/
        parkings.html       # Vue parkings du tenant
        parking_detail.html # Détail parking
        device_whitelist.html # Whitelist avec QR TOTP
      access/
        form.html           # Page publique d'accès par QR code
    static/
      style.css             # CSS minimaliste
      ota/                  # Stockage des packages OTA uploadés

deploy/                    # Filesystem embarqué Jetson
  install.sh               # Installation complète (sudo, one-shot)
  scripts/
    provision.sh           # Configure identité unique du boîtier
    healthcheck.sh         # Vérifie LAPI+MQTT+RAM+disque+temp (timer 60s)
  etc/
    lapi/config.yaml       # Config applicative (inclut section OTA)
    mosquitto/
      mosquitto.conf       # Broker local 127.0.0.1 uniquement
      conf.d/bridge-cloud.conf  # Bridge sortant (whitelist + OTA + access)
    systemd/system/
      lapi.service         # Restart=always, MemoryMax=768M, WatchdogSec=60
      mosquitto.service    # Broker MQTT local
      lapi-healthcheck.*   # Timer + service de health check
    sudoers.d/lapi-ota     # Autorisation restart service pour OTA
    nftables.conf          # Firewall: DROP tout entrant (NFR6)
    NetworkManager/        # Désactive Wi-Fi (NFR5)

systemd/                   # (legacy, remplacé par deploy/etc/systemd/)
  lapi.service
```

## Ce qui est FAIT

### Edge (pipeline vision)
- [x] Inférence ONNX: YOLO voiture, YOLO-pose (4 keypoints plaque), PP-OCRv4
- [x] Tracking Kalman multi-objets (8D véhicule, 4D plaque relative)
- [x] Association greedy (IoU + distance normalisée)
- [x] Warp perspectif plaque → OCR
- [x] CLAHE (normalisation histogramme) avant OCR
- [x] Visualisation debug (boxes, vitesse, keypoints)

### Edge (résilience terrain)
- [x] Service temps réel avec capture caméra (CSI/V4L2/USB)
- [x] Watchdog applicatif (mémoire + heartbeat → SIGTERM)
- [x] Validation regex plaques FR (SIV AA-123-AA) + corrections OCR positionnelles
- [x] Vote multi-trames (3 lectures cohérentes minimum, 60% consensus)
- [x] SQLite whitelist avec cache mémoire (lookup 0.08µs)
- [x] Déclenchement GPIO relais (pulse configurable + cooldown anti-rebond)
- [x] Client MQTT subscriber (réception whitelist, reconnexion auto)

### Edge (OTA)
- [x] Handler OTA complet (download, vérification SHA256, backup, install, rollback)
- [x] Support package tar.gz avec script install.sh personnalisé ou copie auto
- [x] Pruning automatique des anciens backups (garde les 3 derniers)
- [x] Souscription MQTT topic `lapi/ota/update`

### Edge (accès distant)
- [x] Ouverture barrière sur commande MQTT `lapi/access/open` (fallback QR code)

### Web (SaaS)
- [x] Multi-tenant: Admin → Tenants → Users → Parkings → Devices → Whitelist
- [x] Auth JWT (cookies httponly, 2 rôles: admin/tenant)
- [x] Admin panel: CRUD complet (clients, comptes, parkings, dispositifs)
- [x] Dashboard client: vue parkings + gestion whitelist par device
- [x] MQTT publisher: notification temps réel au boîtier (add/remove/sync)
- [x] Interface propre (CSS custom, responsive)
- [x] OTA: upload packages, push par device via MQTT, page admin dédiée
- [x] Accès QR code fallback: page publique `/access/{parking_id}` (plaque + nom)
- [x] TOTP optionnel par parking (Google Authenticator, configurable par parking)
- [x] Rate limiting sur la page d'accès (5 tentatives / 5 min par IP)
- [x] Gestion owner_name + secret TOTP par entrée whitelist
- [x] Génération QR code TOTP dans le dashboard (pour donner au propriétaire)

### Déploiement
- [x] install.sh (paquets, user, venv, configs, services, firewall)
- [x] provision.sh (identité unique du boîtier, credentials MQTT)
- [x] healthcheck.sh (timer 60s, restart après 3 échecs)
- [x] Mosquitto local + bridge sortant cloud (whitelist + OTA + access)
- [x] nftables (aucun port entrant)
- [x] NetworkManager (Wi-Fi désactivé)
- [x] systemd complet (Restart=always, MemoryMax, WatchdogSec)
- [x] sudoers OTA (restart service sans mot de passe)

## Ce qui RESTE à faire

### Priorité 1 — Tests terrain
- [ ] Tester en réseau local (Mosquitto LAN comme broker commun entre web et Jetson)
- [ ] Calibrer les seuils (confiance OCR, min_votes, cooldown GPIO) avec caméra réelle
- [ ] Mesurer la latence end-to-end (objectif < 500ms captation → relais)
- [ ] Valider la résilience (couper le réseau, tuer le process, saturer la mémoire)

### Priorité 2 — Performance (C++)
- [ ] Porter le hot path en C++ (inférence TensorRT + pipeline)
- [ ] Conversion modèles ONNX → TensorRT (.engine) pour le Jetson
- [ ] Benchmark C++ vs Python sur le Jetson

### Priorité 3 — Production web
- [ ] HTTPS (Let's Encrypt / reverse proxy nginx)
- [ ] Migration SQLite → PostgreSQL
- [ ] Déploiement cloud (Docker, CI/CD)
- [ ] Broker MQTT cloud (Mosquitto ou service managé type HiveMQ/EMQX)
- [ ] Sécurité: rate limiting, CSRF tokens, password policy

### Priorité 4 — Fonctionnalités additionnelles
- [ ] Logs d'accès consultables sur le dashboard (historique passages)
- [ ] Alertes (tentative d'accès refusée, boîtier hors ligne)
- [x] OTA updates (mise à jour du firmware/modèles à distance)
- [x] Accès QR code fallback (plaque + nom + TOTP optionnel)
- [ ] Support plaques étrangères (regex configurable par pays)

## Exigences (Requirements)

### Fonctionnelles
| ID | Description | Statut |
|----|-------------|--------|
| FR1 | Captation + inférence jour/nuit | Code fait, à tester terrain |
| FR2 | Filtrage IA (validation multi-trames + regex) | ✅ Done |
| FR3 | Vérification accès < 10ms (SQLite) | ✅ Done (0.08µs) |
| FR4 | Action physique GPIO | ✅ Done |
| FR5 | Administration Cloud (web multi-tenant) | ✅ Done |
| FR6 | Synchronisation MQTT | ✅ Done |
| FR7 | OTA (mise à jour distante des boîtiers) | ✅ Done |
| FR8 | Accès QR code fallback (plaque + nom + TOTP optionnel) | ✅ Done |

### Non-fonctionnelles
| ID | Description | Statut |
|----|-------------|--------|
| NFR1 | Résilience réseau (fonctionne hors-ligne) | ✅ Done |
| NFR2 | Autogestion watchdog + restart auto | ✅ Done |
| NFR3 | Latence < 500ms | À mesurer terrain |
| NFR4 | Sécurité thermique (séparation capteur/LEDs/CPU) | Design only |
| NFR5 | Pas de Wi-Fi (PoE/4G uniquement) | ✅ Done |
| NFR6 | Aucun port entrant | ✅ Done |

## Commandes utiles

```bash
# Web (dev)
cd web && python run.py                    # http://localhost:8000 (admin/admin)

# Edge (test sur fichier)
cd python && python main.py

# Déploiement Jetson
cd deploy && sudo ./install.sh
sudo /opt/lapi/scripts/provision.sh <DEVICE_ID> <MQTT_HOST> <USER> <PASS>

# Logs Jetson
journalctl -u lapi -f
journalctl -u mosquitto -f
```

## Notes techniques

- Python 3.10+ requis (frozen dataclasses, match statements)
- Web: credentials par défaut admin/admin (changer en prod)
- Edge MQTT topics locaux: `lapi/whitelist/{sync|add|remove}`, `lapi/ota/update`, `lapi/access/open`
- Bridge Mosquitto remap: `lapi/{device_id}/{whitelist|ota|access}/X` (cloud) → `lapi/{whitelist|ota|access}/X` (local)
- Le web et la Jetson NE SONT PAS sur le même réseau directement. Il faut un broker MQTT intermédiaire (cloud ou LAN pour les tests)
- OTA: packages stockés dans `web/app/static/ota/`, SHA256 calculé à l'upload, vérification côté edge avant installation
- Accès QR code: page publique `/access/{parking_id}`, rate limité (5 tentatives/5min par IP)
- TOTP: activable par parking (`require_totp`), secret généré par plaque, compatible Google Authenticator
- Dépendances web supplémentaires: `pyotp`, `qrcode[pil]`
