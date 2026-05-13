#!/bin/bash
# Provisionnement d'un boîtier LAPI
# Usage: ./provision.sh <DEVICE_ID> <MQTT_CLOUD_HOST> <MQTT_USER> <MQTT_PASS>
#
# Ce script configure l'identite unique du boitier et sa connexion cloud.

set -euo pipefail

if [ $# -lt 4 ]; then
    echo "Usage: $0 <DEVICE_MQTT_ID> <MQTT_CLOUD_HOST> <MQTT_USERNAME> <MQTT_PASSWORD>"
    echo "Exemple: $0 lapi-edge-001 mqtt.monserveur.com user pass"
    exit 1
fi

DEVICE_ID="$1"
MQTT_HOST="$2"
MQTT_USER="$3"
MQTT_PASS="$4"

echo "[PROVISION] Configuration du boitier: $DEVICE_ID"
echo "[PROVISION] Broker cloud: $MQTT_HOST (MQTTS)"

# 0. Verifier les certificats TLS
CERT_DIR="/etc/lapi/certs"
for f in ca.crt client.crt client.key; do
    if [ ! -f "$CERT_DIR/$f" ]; then
        echo "ERREUR: Certificat manquant: $CERT_DIR/$f"
        echo "Copier ca.crt, client.crt et client.key dans $CERT_DIR/ avant le provisionnement."
        exit 1
    fi
done
chmod 700 "$CERT_DIR"
chmod 600 "$CERT_DIR/client.key"
chmod 644 "$CERT_DIR/ca.crt" "$CERT_DIR/client.crt"
echo "[PROVISION] Certificats TLS verifies"

# 1. Configurer le bridge Mosquitto
BRIDGE_CONF="/etc/mosquitto/conf.d/bridge-cloud.conf"
sed -i "s/__DEVICE_MQTT_ID__/$DEVICE_ID/g" "$BRIDGE_CONF"
sed -i "s/__MQTT_USERNAME__/$MQTT_USER/g" "$BRIDGE_CONF"
sed -i "s/__MQTT_PASSWORD__/$MQTT_PASS/g" "$BRIDGE_CONF"
sed -i "s/mqtt\.example\.com/$MQTT_HOST/g" "$BRIDGE_CONF"
echo "[PROVISION] Bridge MQTT configure"

# 2. Configurer le service LAPI
LAPI_CONF="/etc/lapi/config.yaml"
sed -i "s/client_id: .*/client_id: \"$DEVICE_ID\"/" "$LAPI_CONF"
echo "[PROVISION] Config LAPI mise a jour"

# 3. Generer le mot de passe local Mosquitto
mosquitto_passwd -b /etc/mosquitto/passwd lapi lapi-local-secret
echo "[PROVISION] Credentials MQTT locaux configures"

# 4. Redemarrer les services
systemctl restart mosquitto.service
systemctl restart lapi.service
echo "[PROVISION] Services redemarres"

# 5. Verification
sleep 3
if systemctl is-active --quiet lapi.service && systemctl is-active --quiet mosquitto.service; then
    echo "[PROVISION] OK - Boitier $DEVICE_ID operationnel"
else
    echo "[PROVISION] ERREUR - Verifier les logs: journalctl -u lapi -u mosquitto"
    exit 1
fi
