#!/bin/bash
set -e

echo "🔐 Generating local secrets for development..."

# Create secrets directory
mkdir -p secrets

# Generate RSA key pair for JWT signing
if [ ! -f secrets/jwt-private-key.pem ]; then
    echo "Generating RSA private key..."
    openssl genrsa -out secrets/jwt-private-key.pem 2048
fi

if [ ! -f secrets/jwt-public-key.pem ]; then
    echo "Extracting public key..."
    openssl rsa -in secrets/jwt-private-key.pem -pubout -out secrets/jwt-public-key.pem
fi

echo "✅ Secrets generated in ./secrets/"
echo "   - jwt-private-key.pem (OAuth Server)"
echo "   - jwt-public-key.pem (MCP Server)"
