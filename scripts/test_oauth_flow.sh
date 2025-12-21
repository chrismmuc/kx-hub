#!/bin/bash
set -e

BASE_URL=${1:-http://localhost:8082}

echo "🧪 Testing OAuth 2.1 Flow on $BASE_URL"
echo ""

# Test 1: OAuth Discovery
echo "1️⃣ Testing OAuth Discovery..."
curl -s "$BASE_URL/.well-known/oauth-authorization-server" | python3 -m json.tool
echo "✅ Discovery OK"
echo ""

# Test 2: Client Registration
echo "2️⃣ Testing Client Registration..."
CLIENT_RESPONSE=$(curl -s -X POST "$BASE_URL/register" \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "Test Client",
    "redirect_uris": ["http://localhost:3000/callback"],
    "grant_types": ["authorization_code", "refresh_token"],
    "response_types": ["code"],
    "token_endpoint_auth_method": "client_secret_post",
    "scope": "kx-hub:read"
  }')

echo "$CLIENT_RESPONSE" | python3 -m json.tool

CLIENT_ID=$(echo "$CLIENT_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['client_id'])")
CLIENT_SECRET=$(echo "$CLIENT_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['client_secret'])")

echo "✅ Registration OK"
echo "   Client ID: $CLIENT_ID"
echo ""

# Test 3: Authorization (would open browser in real flow)
echo "3️⃣ Authorization URL:"
AUTH_URL="$BASE_URL/authorize?response_type=code&client_id=$CLIENT_ID&redirect_uri=http://localhost:3000/callback&state=test123&scope=kx-hub:read&code_challenge=test&code_challenge_method=plain"
echo "   $AUTH_URL"
echo "   (Open this in browser to test login)"
echo ""

# Test 4: Token Exchange (requires authorization code from step 3)
echo "4️⃣ Token Exchange:"
echo "   After login, use the authorization code:"
echo "   curl -X POST $BASE_URL/token \\"
echo "     -H 'Content-Type: application/x-www-form-urlencoded' \\"
echo "     -d 'grant_type=authorization_code&code=<CODE>&redirect_uri=http://localhost:3000/callback&client_id=$CLIENT_ID&client_secret=$CLIENT_SECRET&code_verifier=test'"
echo ""

echo "🎉 OAuth server is responding correctly!"
