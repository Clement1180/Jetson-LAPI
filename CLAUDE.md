# LAPI - Lecture Automatique de Plaques d'Immatriculation

## Vue d'ensemble

Dispositif B2B de contrôle d'accès parking par reconnaissance de plaques. Architecture hybride Edge (Jetson) + Cloud (SaaS web).

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  CLOUD (SaaS)                                                   │
│  FastAPI + Jinja2 + SQLAlchemy                                  │
│  Multi-tenant: Admin → Tenants → Parkings → Devices → Whitelist │
│  Publie sur MQTTs: lapi/{device_id}/whitelist/{add|remove|sync}  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ MQTTs (sortant uniquement)
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
    mqtt_client.py         # Subscriber MQTTs (whitelist + OTA + accès distant)
    camera.py              # Capture temps réel (GStreamer CSI/V4L2/USB)
    watchdog.py            # Monitoring mémoire + heartbeat
    ota_handler.py         # Mise à jour OTA (download, SHA256, backup, rollback)

web/                       # Plateforme web SaaS
  run.py                   # Entry point (uvicorn)
  app/
    main.py                # FastAPI app + lifespan
    config.py              # Settings (env vars, Stripe keys, OTA_STORAGE_DIR, WEB_BASE_URL, LAPI_ENV)
    security.py            # CSRF middleware, security headers, rate limiting, password policy, input validation
    database.py            # SQLAlchemy + SQLite/PostgreSQL
    models.py              # ORM: Admin, Tenant, TenantUser, Parking, Device, WhitelistEntry, Subscriber, SubscriptionPlan, Subscription
    auth.py                # JWT cookies + hash password (3 rôles: admin/tenant/subscriber)
    mqtt_publisher.py      # Publie vers les devices via MQTT (whitelist + OTA + accès)
    templates_env.py       # Jinja2 templates partagé + filtre timestamp_to_date
    subscription_sync.py   # Sync abonnement → whitelist MQTT + vérification expirations + avertissements
    email_service.py       # Service email SMTP (confirmation paiement, avertissement expiration, notification gestionnaire)
    routers/
      auth_routes.py       # Login/logout (admin, tenant, subscriber register/login)
      admin.py             # CRUD tenants/users/parkings/devices + OTA upload/push
      dashboard.py         # Gestion whitelist + CRUD plans d'abonnement par parking
      access.py            # Page publique accès QR code (plaque + nom + TOTP optionnel)
      subscribe.py         # Espace abonné: liste parkings, plans, checkout Stripe, compte, annulation
      stripe_webhook.py    # Webhook Stripe (checkout.session.completed, invoice.payment_failed)
    templates/
      login.html           # Page de connexion (admin/tenant)
      base.html            # Layout de base
      admin/
        tenants.html        # Liste des clients
        tenant_detail.html  # Détail client (users, parkings, devices, OTA)
        ota.html            # Upload et liste des packages OTA
      dashboard/
        parkings.html       # Vue parkings du tenant
        parking_detail.html # Détail parking + lien gestion abonnements
        device_whitelist.html # Whitelist avec QR TOTP
        plans.html          # CRUD plans d'abonnement (prix, durée, renouvellement)
      subscribe/
        register.html       # Inscription abonné (email, plaque, mot de passe)
        login.html          # Connexion abonné
        parkings.html       # Liste des parkings avec abonnements disponibles
        plans.html          # Choix du plan + option renouvellement auto
        account.html        # Compte abonné (abonnements actifs, annulation, toggle renew)
        success.html        # Confirmation paiement / activation
      access/
        form.html           # Page publique d'accès par QR code
    static/
      style.css             # CSS (+ grilles plans/parkings, checkboxes, badges warning)
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
      mosquitto.service    # Broker MQTTs local
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
- [x] Client MQTTs subscriber (réception whitelist, reconnexion auto)

### Edge (OTA)
- [x] Handler OTA complet (download, vérification SHA256, backup, install, rollback)
- [x] Support package tar.gz avec script install.sh personnalisé ou copie auto
- [x] Pruning automatique des anciens backups (garde les 3 derniers)
- [x] Souscription MQTT topic `lapi/ota/update`

### Edge (accès distant)
- [x] Ouverture barrière sur commande MQTT `lapi/access/open` (fallback QR code)

### Web (SaaS)
- [x] Multi-tenant: Admin → Tenants → Users → Parkings → Devices → Whitelist
- [x] Auth JWT (cookies httponly, 3 rôles: admin/tenant/subscriber)
- [x] Admin panel: CRUD complet (clients, comptes, parkings, dispositifs)
- [x] Dashboard client: vue parkings + gestion whitelist par device
- [x] MQTTs publisher: notification temps réel au boîtier (add/remove/sync)
- [x] Interface propre (CSS custom, responsive)
- [x] OTA: upload packages, push par device via MQTT, page admin dédiée
- [x] Accès QR code fallback: page publique `/access/{parking_id}` (plaque + nom)
- [x] TOTP optionnel par parking (Google Authenticator, configurable par parking)
- [x] Rate limiting sur la page d'accès (5 tentatives / 5 min par IP)
- [x] Gestion owner_name + secret TOTP par entrée whitelist
- [x] Génération QR code TOTP dans le dashboard (pour donner au propriétaire)

### Web (Abonnements parking payant)
- [x] Modèles: Subscriber (compte abonné), SubscriptionPlan (plan tarifaire), Subscription (abonnement)
- [x] Inscription/connexion abonné (email + plaque d'immatriculation)
- [x] Espace abonné: liste parkings disponibles, choix du plan, gestion compte
- [x] Paiement Stripe: Checkout Session + webhook (checkout.session.completed, invoice.payment_failed)
- [x] Mode dev sans Stripe: activation directe de l'abonnement (si STRIPE_SECRET_KEY vide)
- [x] Plans configurables par le gestionnaire: nom, durée (jour/semaine/mois/trimestre/année), prix
- [x] Renouvellement automatique optionnel (activable par l'abonné si le plan le permet)
- [x] Sync abonnement → whitelist: activation = ajout plaque sur tous les devices du parking via MQTT
- [x] Expiration automatique: tâche async toutes les 5 min, retire les plaques expirées
- [x] Annulation d'abonnement avec retrait de la plaque de la whitelist
- [x] Protection contre double-activation (vérification Stripe session_id unique)
- [x] Dashboard tenant: page CRUD plans d'abonnement avec compteur abonnés actifs
- [x] Email confirmation de paiement à l'abonné (récapitulatif complet)
- [x] Email notification au gestionnaire de parking lors d'un nouvel abonnement
- [x] Email avertissement 5 jours avant expiration (avec flag anti-doublon)

### Déploiement
- [x] install.sh (paquets, user, venv, configs, services, firewall)
- [x] provision.sh (identité unique du boîtier, credentials MQTT)
- [x] healthcheck.sh (timer 60s, restart après 3 échecs)
- [x] Mosquitto local + bridge sortant cloud (whitelist + OTA + access)
- [x] nftables (aucun port entrant)
- [x] NetworkManager (Wi-Fi désactivé)
- [x] systemd complet (Restart=always, MemoryMax, WatchdogSec)
- [x] sudoers OTA (restart service sans mot de passe)

## Ce qui est FAIT (Priorités 0–3)

### Priorité 0 — Sécurité ✅
- [x] Protection CSRF sur tous les formulaires POST (admin, dashboard, subscribe, access)
- [x] Headers sécurité: X-Frame-Options, X-Content-Type-Options, Strict-Transport-Security, Content-Security-Policy
- [x] Supprimer les credentials admin hardcodés (`admin/admin`), forcer la création au premier lancement
- [x] Rendre SECRET_KEY obligatoire (crash si env var absente, pas de valeur par défaut)
- [x] Politique mot de passe renforcée (min 12 chars, majuscule, chiffre, spécial)
- [x] Rate limiting sur `/login`, `/subscribe/login`, `/subscribe/register` (brute force)
- [x] Vérification signature Stripe webhook obligatoire (crash si `STRIPE_WEBHOOK_SECRET` vide en prod)
- [x] Échapper les données utilisateur dans les templates email (injection HTML)
- [x] Validation/sanitization des entrées dans tous les routers (longueur, format, types)

### Priorité 1 — Tests & Qualité ✅
- [x] Suite de tests pytest — 95 tests (auth, paiements, rate limiting, CRUD whitelist, sync MQTT)
- [x] Tests d'intégration Stripe (webhook, checkout flow, expiration)
- [x] Tests edge: validation plaque, vote multi-trames, base whitelist
- [x] Fichier `.env.example` documentant toutes les env vars requises
- [x] Endpoint `/health` sur le web (pour monitoring externe)
- [x] Gestion d'erreurs globale (exception handler, logging, pages 404/500 custom)

### Priorité 2 — Infrastructure & Déploiement ✅
- [x] Migrations DB avec Alembic (`web/alembic/`) — auto-migration en prod, `create_all()` en dev
- [x] Support PostgreSQL (prod) + SQLite (dev) — via `LAPI_DATABASE_URL`
- [x] Dockerfile + docker-compose (web + MQTT broker MQTTS + PostgreSQL)
- [x] Pipeline CI/CD GitHub Actions (`.github/workflows/ci.yml`): lint, tests, build Docker, health check
- [x] Broker MQTTs cloud via docker-compose (Mosquitto, TLS sur port 8883, auth password)
- [x] Logging structuré JSON en prod (`web/app/logging_config.py`), texte en dev
- [x] Intégration Sentry (via env `SENTRY_DSN`, optionnel)
- [x] Script génération certificats TLS (`deploy/docker/generate-certs.sh`)

### Priorité 3 — Tests terrain ✅
- [x] Tests réseau LAN MQTTS (`tests/terrain/test_lan_mqtt.py`) — pub/sub, round-trip, latence
- [x] Fichier de calibration (`tests/terrain/calibration.yaml`) — seuils OCR, vote, GPIO, caméra
- [x] Benchmark latence end-to-end (`tests/terrain/test_latency.py`) — validation 2.4µs, voter 10µs, lookup 54ns, pipeline 19µs
- [x] Tests résilience (`tests/terrain/test_resilience.py`) — hors-ligne, écritures concurrentes, crash DB, kill service

## Ce qui RESTE à faire

### Avant mise en prod (bloquant)
- [ ] HTTPS obligatoire: configurer nginx/caddy en reverse proxy avec Let's Encrypt + redirect HTTP→HTTPS
- [ ] Générer les certificats MQTTS (`deploy/docker/generate-certs.sh`) et créer le fichier `passwd` Mosquitto
- [ ] Premier déploiement `docker-compose up` avec un vrai fichier `.env`
- [ ] Corriger le mot de passe edge MQTT hardcodé (`deploy/install.sh:89`: `lapi-local-secret` en clair)

### Priorité 4 — Performance (C++) — Sur Jetson uniquement
- [ ] Porter le hot path en C++ (inférence TensorRT + pipeline)
- [ ] Conversion modèles ONNX → TensorRT (.engine) pour le Jetson
- [ ] Benchmark C++ vs Python sur le Jetson

### Priorité 5 — Fonctionnalités additionnelles
- [ ] **Multi-plaques par abonné** (actuellement 1 plaque/compte — nécessite table `subscriber_plates`)
- [ ] **Logs d'accès consultables sur le dashboard** (historique passages, remontée edge → cloud via MQTT)
- [ ] **Alertes** (tentative d'accès refusée, boîtier hors ligne — notification temps réel au gestionnaire)
- [ ] **Audit trail admin** (log des actions: modifications whitelist, connexions, changements config)
- [ ] Historique des paiements dans l'espace abonné (modèle Payment/Invoice)
- [ ] Gestion des remboursements Stripe (logique refund dans webhook)
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
| FR9 | Abonnements parking payant (inscription, paiement Stripe, durée configurable) | ✅ Done |
| FR10 | Sync auto abonnement → whitelist (activation/expiration/annulation) | ✅ Done |
| FR11 | Gestion plans tarifaires par le gestionnaire (CRUD, durée, prix) | ✅ Done |
| FR12 | Multi-plaques par abonné | ❌ À faire (1 plaque/compte actuellement) |
| FR13 | Historique des paiements (modèle Payment/Invoice) | ❌ À faire |
| FR14 | Logs d'accès consultables sur dashboard (remontée edge → cloud) | ❌ À faire |
| FR15 | Audit trail admin (log actions, connexions, modifications) | ❌ À faire |

### Non-fonctionnelles
| ID | Description | Statut |
|----|-------------|--------|
| NFR1 | Résilience réseau (fonctionne hors-ligne) | ✅ Done |
| NFR2 | Autogestion watchdog + restart auto | ✅ Done |
| NFR3 | Latence < 500ms | À mesurer terrain |
| NFR4 | Sécurité thermique (séparation capteur/LEDs/CPU) | Design only |
| NFR5 | Pas de Wi-Fi (PoE/4G uniquement) | ✅ Done |
| NFR6 | Aucun port entrant | ✅ Done |
| NFR7 | Protection CSRF sur tous les formulaires | ✅ Done |
| NFR8 | HTTPS obligatoire + headers sécurité | ⚠️ Headers done, HTTPS = reverse proxy |
| NFR9 | Politique mot de passe renforcée | ✅ Done |
| NFR10 | Rate limiting sur toutes les routes auth | ✅ Done |
| NFR11 | Suite de tests automatisés (pytest) | ✅ Done (86 tests) |
| NFR12 | Migrations DB versionnées (Alembic) | ✅ Done |
| NFR13 | Déploiement conteneurisé (Docker + CI/CD) | ✅ Done |
| NFR14 | Logging structuré + monitoring centralisé | ✅ Done |

## Commandes utiles

```bash
# Web (dev)
cd web && LAPI_ADMIN_USERNAME=admin LAPI_ADMIN_PASSWORD='Admin1234!@#' python run.py

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
- Web: admin créé via env vars `LAPI_ADMIN_USERNAME` + `LAPI_ADMIN_PASSWORD` (obligatoire au 1er lancement)
- Edge MQTT topics locaux: `lapi/whitelist/{sync|add|remove}`, `lapi/ota/update`, `lapi/access/open`
- Bridge Mosquitto remap: `lapi/{device_id}/{whitelist|ota|access}/X` (cloud) → `lapi/{whitelist|ota|access}/X` (local)
- Le web et la Jetson NE SONT PAS sur le même réseau directement. Il faut un broker MQTT intermédiaire (cloud ou LAN pour les tests)
- OTA: packages stockés dans `web/app/static/ota/`, SHA256 calculé à l'upload, vérification côté edge avant installation
- Accès QR code: page publique `/access/{parking_id}`, rate limité (5 tentatives/5min par IP)
- TOTP: activable par parking (`require_totp`), secret généré par plaque, compatible Google Authenticator
- Dépendances web supplémentaires: `pyotp`, `qrcode[pil]`, `stripe` (optionnel, mode dev sans)
- SMTP: configurable via env vars `LAPI_SMTP_HOST`, `LAPI_SMTP_PORT`, `LAPI_SMTP_USERNAME`, `LAPI_SMTP_PASSWORD`, `LAPI_SMTP_FROM`, `LAPI_SMTP_USE_TLS`
- Si SMTP non configuré, les emails sont loggés mais non envoyés (pas de crash)
- Emails envoyés en arrière-plan (thread) pour ne pas bloquer les requêtes
- Email d'avertissement envoyé 5 jours avant expiration (flag `expiry_warning_sent` pour éviter les doublons)
- Email de notification gestionnaire: envoyé au `contact_email` du tenant (ignoré si vide)
- Abonnements: 3 nouveaux modèles (Subscriber, SubscriptionPlan, Subscription) + enums SubscriptionStatus, PlanDuration
- Subscriber auth: rôle JWT `subscriber`, routes `/subscribe/register` et `/subscribe/login`
- Stripe: configurable via env vars `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`
- Stripe webhook endpoint: `POST /webhook/stripe` (à configurer dans le dashboard Stripe)
- Mode dev sans Stripe: si `STRIPE_SECRET_KEY` est vide, l'abonnement est activé directement sans paiement
- Durées d'abonnement supportées: daily, weekly, monthly, quarterly, yearly (calculées en secondes fixes)
- Tâche async d'expiration: vérifie toutes les 5 min, expire ou renouvelle les abonnements
- Sync whitelist: un abonnement actif = plaque ajoutée sur tous les devices du parking concerné
- Annulation: retire la plaque uniquement s'il n'existe pas d'autre abonnement actif sur le même parking
- Espace abonné public: `/subscribe/parkings`, `/subscribe/parking/{id}`, `/subscribe/account`
- Dashboard tenant: gestion plans via `/dashboard/parking/{id}/plans`
- Sécurité: module `security.py` centralise CSRF, headers, rate limiting, validation
- `LAPI_ENV=production` active les contrôles stricts (SECRET_KEY obligatoire, Stripe webhook obligatoire, password policy sur admin)
- CSRF: cookie `csrf_token` + champ hidden `csrf_token` dans tous les formulaires POST, rotation à chaque requête POST
- Headers sécurité: X-Frame-Options DENY, X-Content-Type-Options nosniff, CSP, HSTS (si HTTPS)
- Rate limiting auth: 5 tentatives / 5 min par IP sur `/login`, `/subscribe/login`, `/subscribe/register`
- Password policy: min 12 caractères, 1 majuscule, 1 chiffre, 1 caractère spécial
- Validation entrées: email (regex + longueur), plaque (format SIV AA-123-AA), strings sanitisées (trim + max_length)

## Vulnérabilités connues (à corriger avant prod)

- ~~**CSRF**: aucun token CSRF sur les formulaires POST~~ ✅ Corrigé (middleware + token cookie/form)
- ~~**Credentials hardcodés**: `admin/admin` dans `config.py`~~ ✅ Corrigé (env vars obligatoires)
- ~~**SECRET_KEY par défaut**~~ ✅ Corrigé (crash en prod si absent)
- ~~**Webhook Stripe non vérifié**~~ ✅ Corrigé (rejeté en prod si secret absent)
- ~~**Injection HTML emails**~~ ✅ Corrigé (`html.escape()` sur toutes les données utilisateur)
- ~~**Pas de rate limiting sur login**~~ ✅ Corrigé (5 tentatives / 5 min par IP)
- ~~**Pas de validation d'entrée côté serveur**~~ ✅ Corrigé (longueur, format email, plaque, types)
- **Mot de passe edge MQTT hardcodé**: `deploy/install.sh:89` contient `lapi-local-secret` en clair
- **HTTPS**: l'application ne gère pas le TLS elle-même, nécessite un reverse proxy (nginx/caddy) avec Let's Encrypt
