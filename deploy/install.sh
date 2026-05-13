#!/bin/bash
# Installation complete du systeme LAPI sur Jetson
# Executer en root sur un Jetson fraichement flashe avec JetPack.
#
# Usage: sudo ./install.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="/opt/lapi"

echo "============================================"
echo "  LAPI - Installation du systeme embarque"
echo "============================================"
echo ""

# Verifier root
if [ "$(id -u)" -ne 0 ]; then
    echo "ERREUR: Executer en root (sudo ./install.sh)"
    exit 1
fi

# -----------------------------------------------------------
# 1. PAQUETS SYSTEME
# -----------------------------------------------------------
echo "[1/8] Installation des paquets systeme..."
apt-get update -qq
apt-get install -y -qq \
    mosquitto mosquitto-clients \
    python3-pip python3-venv \
    sqlite3 \
    nftables \
    network-manager \
    libgstreamer1.0-0 gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good gstreamer1.0-tools

# Desactiver le Wi-Fi au niveau kernel (NFR5)
if command -v rfkill &>/dev/null; then
    rfkill block wifi 2>/dev/null || true
fi

# -----------------------------------------------------------
# 2. UTILISATEUR ET GROUPES
# -----------------------------------------------------------
echo "[2/8] Creation utilisateur lapi..."
if ! id -u lapi &>/dev/null; then
    useradd -r -s /usr/sbin/nologin -d /opt/lapi -m lapi
fi
usermod -aG video,gpio,i2c lapi 2>/dev/null || true

# -----------------------------------------------------------
# 3. ARBORESCENCE
# -----------------------------------------------------------
echo "[3/8] Creation de l'arborescence..."
mkdir -p "$INSTALL_DIR"/{python,models,scripts,venv}
mkdir -p /var/lib/lapi/ota
mkdir -p /var/log/lapi
mkdir -p /var/lib/mosquitto
mkdir -p /etc/lapi/certs
mkdir -p /etc/mosquitto/conf.d
mkdir -p /etc/sudoers.d

# -----------------------------------------------------------
# 4. COPIE DU CODE APPLICATIF
# -----------------------------------------------------------
echo "[4/8] Deploiement du code..."
cp -r "$SCRIPT_DIR/../python/src" "$INSTALL_DIR/python/"
cp "$SCRIPT_DIR/../python/service.py" "$INSTALL_DIR/python/"
cp "$SCRIPT_DIR/../python/requirements.txt" "$INSTALL_DIR/python/"

# Environnement virtuel Python
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/python/requirements.txt" -q
echo "   Python venv installe"

# Scripts utilitaires
cp "$SCRIPT_DIR/scripts/"*.sh "$INSTALL_DIR/scripts/"
chmod +x "$INSTALL_DIR/scripts/"*.sh

# -----------------------------------------------------------
# 5. CONFIGURATION
# -----------------------------------------------------------
echo "[5/8] Installation des configurations..."
# Mosquitto
cp "$SCRIPT_DIR/etc/mosquitto/mosquitto.conf" /etc/mosquitto/
cp "$SCRIPT_DIR/etc/mosquitto/conf.d/bridge-cloud.conf" /etc/mosquitto/conf.d/
touch /etc/mosquitto/passwd
mosquitto_passwd -b /etc/mosquitto/passwd lapi lapi-local-secret

# LAPI
cp "$SCRIPT_DIR/etc/lapi/config.yaml" /etc/lapi/

# Sudoers pour OTA (restart du service sans mot de passe)
cp "$SCRIPT_DIR/etc/sudoers.d/lapi-ota" /etc/sudoers.d/lapi-ota
chmod 440 /etc/sudoers.d/lapi-ota

# Firewall
cp "$SCRIPT_DIR/etc/nftables.conf" /etc/nftables.conf

# NetworkManager (desactive Wi-Fi)
cp "$SCRIPT_DIR/etc/NetworkManager/conf.d/10-lapi-security.conf" \
   /etc/NetworkManager/conf.d/ 2>/dev/null || true

# -----------------------------------------------------------
# 6. SERVICES SYSTEMD
# -----------------------------------------------------------
echo "[6/8] Installation des services systemd..."
cp "$SCRIPT_DIR/etc/systemd/system/lapi.service" /etc/systemd/system/
cp "$SCRIPT_DIR/etc/systemd/system/mosquitto.service" /etc/systemd/system/
cp "$SCRIPT_DIR/etc/systemd/system/lapi-healthcheck.service" /etc/systemd/system/
cp "$SCRIPT_DIR/etc/systemd/system/lapi-healthcheck.timer" /etc/systemd/system/

systemctl daemon-reload
systemctl enable mosquitto.service
systemctl enable lapi.service
systemctl enable lapi-healthcheck.timer
systemctl enable nftables.service

# -----------------------------------------------------------
# 7. PERMISSIONS
# -----------------------------------------------------------
echo "[7/8] Application des permissions..."
chown -R lapi:lapi "$INSTALL_DIR"
chown -R lapi:lapi /var/lib/lapi
chown -R lapi:lapi /var/lib/lapi/ota
chown -R lapi:lapi /var/log/lapi
chown -R mosquitto:mosquitto /var/lib/mosquitto
chown -R mosquitto:mosquitto /etc/mosquitto/passwd
chmod 600 /etc/mosquitto/passwd
chmod 700 /etc/lapi/certs
chmod 600 /etc/lapi/certs/*.key 2>/dev/null || true
chmod 644 /etc/lapi/certs/*.crt 2>/dev/null || true
chmod 700 "$INSTALL_DIR/scripts/"

# -----------------------------------------------------------
# 8. ACTIVATION FIREWALL
# -----------------------------------------------------------
echo "[8/8] Activation du firewall..."
systemctl start nftables.service
nft -f /etc/nftables.conf

echo ""
echo "============================================"
echo "  INSTALLATION TERMINEE"
echo "============================================"
echo ""
echo "Prochaines etapes:"
echo "  1. Copier les modeles ONNX dans $INSTALL_DIR/models/"
echo "  2. Copier les certificats TLS dans /etc/lapi/certs/"
echo "     ca.crt (CA), client.crt (certificat client), client.key (cle privee)"
echo "  3. Provisionner le boitier:"
echo "     $INSTALL_DIR/scripts/provision.sh <DEVICE_ID> <MQTT_HOST> <USER> <PASS>"
echo "  4. Demarrer les services:"
echo "     systemctl start mosquitto && systemctl start lapi"
echo ""
echo "Commandes utiles:"
echo "  journalctl -u lapi -f            # Logs temps reel"
echo "  journalctl -u mosquitto -f       # Logs MQTT"
echo "  systemctl status lapi            # Etat du service"
echo "  $INSTALL_DIR/scripts/healthcheck.sh  # Check manuel"
echo ""
