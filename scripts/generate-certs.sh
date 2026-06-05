#!/bin/bash
# Generate self-signed certificate for development/testing
mkdir -p certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout certs/server.key \
  -out certs/server.crt \
  -subj "/CN=localhost/O=iCoDer/C=CN"
echo "Certificates generated in ./certs/"
echo "server.crt — self-signed certificate"
echo "server.key — private key"
