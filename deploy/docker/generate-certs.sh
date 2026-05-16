#!/bin/bash
# Génère les certificats TLS pour le broker MQTTS
# Usage: ./generate-certs.sh [domain]

set -e

DOMAIN="${1:-mqtt.lapi.local}"
CERTS_DIR="$(dirname "$0")/certs"
mkdir -p "$CERTS_DIR"

echo "==> Generation CA..."
openssl req -new -x509 -days 3650 -extensions v3_ca \
    -keyout "$CERTS_DIR/ca.key" -out "$CERTS_DIR/ca.crt" \
    -subj "/CN=LAPI MQTT CA" -nodes

echo "==> Generation cle serveur..."
openssl genrsa -out "$CERTS_DIR/server.key" 2048

echo "==> Generation CSR serveur..."
openssl req -new -key "$CERTS_DIR/server.key" -out "$CERTS_DIR/server.csr" \
    -subj "/CN=$DOMAIN"

echo "==> Signature certificat serveur..."
openssl x509 -req -in "$CERTS_DIR/server.csr" \
    -CA "$CERTS_DIR/ca.crt" -CAkey "$CERTS_DIR/ca.key" -CAcreateserial \
    -out "$CERTS_DIR/server.crt" -days 3650

rm -f "$CERTS_DIR/server.csr" "$CERTS_DIR/ca.srl"
chmod 600 "$CERTS_DIR"/*.key

echo "==> Certificats generes dans $CERTS_DIR/"
echo "    ca.crt      - CA (a copier sur les Jetson)"
echo "    server.crt  - Certificat serveur"
echo "    server.key  - Cle privee serveur"
echo ""
echo "Pour creer le fichier passwd Mosquitto:"
echo "    docker run --rm eclipse-mosquitto:2 mosquitto_passwd -c /dev/stdout lapi-edge"
