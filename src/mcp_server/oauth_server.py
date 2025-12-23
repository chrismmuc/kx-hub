"""
OAuth 2.1 Authorization Server with Dynamic Client Registration (RFC 7591).

Implements OAuth endpoints for Claude.ai Mobile and Web access to kx-hub MCP server.
"""

import os
import jwt
import hashlib
import base64
from typing import Optional
from datetime import datetime, timedelta, timezone
from starlette.responses import JSONResponse, HTMLResponse, RedirectResponse
from starlette.requests import Request
from google.cloud import secretmanager

from oauth_storage import OAuthStorage
from oauth_templates import get_login_page, get_consent_page, get_error_page, get_success_page

import logging

logger = logging.getLogger(__name__)


class OAuthServer:
    """OAuth 2.1 Authorization Server."""

    def __init__(self):
        """Initialize OAuth server."""
        self.storage = OAuthStorage()
        self.project_id = os.getenv("GCP_PROJECT")

        # Issuer URL must be HTTPS for security (required by OAuth 2.1)
        self.issuer = os.getenv("OAUTH_ISSUER")
        if self.issuer and not self.issuer.startswith("https://"):
            raise ValueError(
                f"OAUTH_ISSUER must use HTTPS (got: {self.issuer}). "
                "Set OAUTH_ISSUER to your Cloud Run service URL (e.g., https://your-service.run.app)"
            )

        self.authorized_user_email = os.getenv("OAUTH_USER_EMAIL")
        self.authorized_password_hash = os.getenv("OAUTH_USER_PASSWORD_HASH")  # bcrypt hash
        self.secret_client = secretmanager.SecretManagerServiceClient()
        self._private_key = None

    # ==================== Utilities ====================

    def get_base_url_from_request(self, request: Request) -> str:
        """
        Extract base URL from request, handling Cloud Run's X-Forwarded-Proto.

        Args:
            request: Starlette Request object

        Returns:
            Base URL with correct protocol (https:// for Cloud Run)
        """
        base_url = str(request.base_url).rstrip("/")

        # Cloud Run uses X-Forwarded-Proto to indicate original protocol
        if base_url.startswith("http://") and request.headers.get("x-forwarded-proto") == "https":
            base_url = base_url.replace("http://", "https://", 1)

        return base_url

    def get_issuer(self, request: Optional[Request] = None) -> str:
        """
        Get OAuth issuer URL.

        Args:
            request: Optional Starlette Request object

        Returns:
            Issuer URL (configured or derived from request)

        Raises:
            ValueError: If no issuer configured and no request provided
        """
        if self.issuer:
            return self.issuer

        if request:
            base_url = self.get_base_url_from_request(request)

            # Ensure HTTPS for security
            if not base_url.startswith("https://"):
                logger.warning(
                    f"Issuer URL is not HTTPS (got: {base_url}). "
                    "This may cause JWT validation failures. "
                    "Set OAUTH_ISSUER environment variable to your HTTPS URL."
                )

            return base_url

        # No issuer configured and no request - this is an error
        raise ValueError(
            "OAUTH_ISSUER environment variable not set and no request context available. "
            "Set OAUTH_ISSUER to your Cloud Run service URL (e.g., https://your-service.run.app)"
        )

    def get_private_key(self) -> str:
        """
        Get RSA private key from Secret Manager.

        Returns:
            PEM-encoded private key
        """
        if self._private_key:
            return self._private_key

        secret_name = f"projects/{self.project_id}/secrets/oauth-jwt-private-key/versions/latest"

        try:
            response = self.secret_client.access_secret_version(request={"name": secret_name})
            self._private_key = response.payload.data.decode("UTF-8")
            logger.info("Loaded OAuth JWT private key from Secret Manager")
            return self._private_key
        except Exception as e:
            logger.error(f"Failed to load JWT private key: {e}")
            raise

    def get_public_key(self) -> str:
        """
        Get RSA public key from Secret Manager for JWT verification.

        Returns:
            PEM-encoded public key
        """
        if not hasattr(self, '_public_key') or self._public_key is None:
            secret_name = f"projects/{self.project_id}/secrets/oauth-jwt-public-key/versions/latest"

            try:
                response = self.secret_client.access_secret_version(request={"name": secret_name})
                self._public_key = response.payload.data.decode("UTF-8")
                logger.info("Loaded OAuth JWT public key from Secret Manager")
            except Exception as e:
                logger.error(f"Failed to load JWT public key: {e}")
                raise

        return self._public_key

    def create_jwt_token(
        self,
        user_id: str,
        client_id: str,
        scope: str,
        expires_in: int = 3600
    ) -> str:
        """
        Create JWT access token.

        Args:
            user_id: User identifier
            client_id: Client identifier
            scope: Token scope
            expires_in: Token expiry in seconds (default 1 hour)

        Returns:
            JWT access token
        """
        private_key = self.get_private_key()

        now = datetime.now(timezone.utc)
        payload = {
            "iss": self.issuer,
            "sub": user_id,
            "aud": client_id,
            "client_id": client_id,
            "scope": scope,
            "iat": now,
            "exp": now + timedelta(seconds=expires_in),
            "token_type": "Bearer"
        }

        token = jwt.encode(payload, private_key, algorithm="RS256")
        return token

    def verify_pkce_challenge(
        self,
        code_verifier: str,
        code_challenge: str,
        code_challenge_method: str
    ) -> bool:
        """
        Verify PKCE code challenge.

        Args:
            code_verifier: Code verifier from token request
            code_challenge: Code challenge from authorization request
            code_challenge_method: Challenge method (plain or S256)

        Returns:
            True if challenge is valid
        """
        if code_challenge_method == "plain":
            return code_verifier == code_challenge

        elif code_challenge_method == "S256":
            computed_challenge = base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode()).digest()
            ).decode().rstrip("=")
            return computed_challenge == code_challenge

        return False

    # ==================== RFC 7591: Dynamic Client Registration ====================

    async def register_client(self, request: Request) -> JSONResponse:
        """
        Dynamic Client Registration endpoint (RFC 7591).

        POST /register

        Request body:
            {
                "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
                "client_name": "Claude",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "client_secret_post",
                "scope": "kx-hub:read"
            }

        Returns:
            Client registration response with client_id and client_secret
        """
        try:
            body = await request.json()

            # Validate required fields
            redirect_uris = body.get("redirect_uris")
            client_name = body.get("client_name")

            if not redirect_uris or not client_name:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "invalid_client_metadata",
                        "error_description": "redirect_uris and client_name are required"
                    }
                )

            # Register client
            registration = self.storage.register_client(
                redirect_uris=redirect_uris,
                client_name=client_name,
                grant_types=body.get("grant_types"),
                response_types=body.get("response_types"),
                scope=body.get("scope")
            )

            logger.info(f"Client registered: {client_name} with redirect_uris: {redirect_uris}")

            # RFC 7591 response
            return JSONResponse(
                status_code=201,
                content=registration
            )

        except Exception as e:
            logger.error(f"Client registration failed: {e}")
            return JSONResponse(
                status_code=500,
                content={
                    "error": "server_error",
                    "error_description": str(e)
                }
            )

    # ==================== OAuth 2.1 Authorization Endpoint ====================

    async def authorize(self, request: Request) -> HTMLResponse:
        """
        OAuth authorization endpoint.

        GET /authorize?client_id=...&redirect_uri=...&response_type=code&state=...&scope=...&code_challenge=...&code_challenge_method=S256

        Shows login/consent page to user.
        """
        # Parse query parameters
        client_id = request.query_params.get("client_id")
        redirect_uri = request.query_params.get("redirect_uri")
        response_type = request.query_params.get("response_type")
        state = request.query_params.get("state")
        scope = request.query_params.get("scope", "")
        code_challenge = request.query_params.get("code_challenge")
        code_challenge_method = request.query_params.get("code_challenge_method", "S256")

        logger.info(f"Authorization request: client_id={client_id}, redirect_uri={redirect_uri}, scope={scope}")

        # Validate required parameters
        if not all([client_id, redirect_uri, response_type, state]):
            return HTMLResponse(
                content=get_error_page(
                    "invalid_request",
                    "Missing required parameters: client_id, redirect_uri, response_type, or state"
                ),
                status_code=400
            )

        # Validate client
        client = self.storage.get_client(client_id)
        if not client:
            return HTMLResponse(
                content=get_error_page("invalid_client", "Unknown client_id"),
                status_code=400
            )

        # Validate redirect_uri
        if not self.storage.validate_redirect_uri(client_id, redirect_uri):
            return HTMLResponse(
                content=get_error_page(
                    "invalid_request",
                    "redirect_uri is not registered for this client"
                ),
                status_code=400
            )

        # Validate response_type
        if response_type != "code":
            error_url = f"{redirect_uri}?error=unsupported_response_type&state={state}"
            return RedirectResponse(url=error_url)

        # Handle POST (user submits password or consent)
        if request.method == "POST":
            form_data = await request.form()

            # Check if this is consent approval (after successful login)
            if form_data.get("consent") == "approve":
                # User approved, create authorization code
                user_id = self.authorized_user_email  # Single-user system

                code = self.storage.create_authorization_code(
                    client_id=client_id,
                    redirect_uri=redirect_uri,
                    scope=scope,
                    user_id=user_id,
                    code_challenge=code_challenge,
                    code_challenge_method=code_challenge_method
                )

                # Build redirect URL with authorization code
                redirect_url = f"{redirect_uri}?code={code}&state={state}"
                logger.info(f"Authorization granted for client: {client['client_name']}, redirecting to: {redirect_uri}")

                # Show success page with auto-redirect (better UX than immediate redirect)
                logger.info(f"Showing success page for client: {client['client_name']}")
                return HTMLResponse(
                    content=get_success_page(
                        redirect_url=redirect_url,
                        client_name=client["client_name"]
                    )
                )

            # Check password (login form submitted)
            password = form_data.get("password")

            if not password:
                return HTMLResponse(
                    content=get_login_page(
                        client_name=client["client_name"],
                        scope=scope,
                        error="Password is required"
                    )
                )

            # Validate password (simple password check for single-user)
            # In production, you'd validate against bcrypt hash or use Google Sign-In
            import bcrypt
            if not bcrypt.checkpw(password.encode(), self.authorized_password_hash.encode()):
                return HTMLResponse(
                    content=get_login_page(
                        client_name=client["client_name"],
                        scope=scope,
                        error="Invalid password"
                    )
                )

            # Password valid, show consent page
            return HTMLResponse(
                content=get_consent_page(
                    client_name=client["client_name"],
                    scope=scope or "Read access to kx-hub knowledge base",
                    user_email=self.authorized_user_email
                )
            )

        # GET request: show login page
        return HTMLResponse(
            content=get_login_page(
                client_name=client["client_name"],
                scope=scope or "Read access to kx-hub knowledge base"
            )
        )

    # ==================== OAuth 2.1 Token Endpoint ====================

    async def token(self, request: Request) -> JSONResponse:
        """
        OAuth token endpoint.

        POST /token

        Supports:
        - authorization_code grant (exchange code for tokens)
        - refresh_token grant (refresh access token)
        """
        try:
            form_data = await request.form()

            grant_type = form_data.get("grant_type")
            client_id = form_data.get("client_id")
            client_secret = form_data.get("client_secret")

            # Validate client credentials
            if not client_id or not client_secret:
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": "invalid_client",
                        "error_description": "Missing client credentials"
                    }
                )

            if not self.storage.validate_client_secret(client_id, client_secret):
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": "invalid_client",
                        "error_description": "Invalid client credentials"
                    }
                )

            # Handle authorization_code grant
            if grant_type == "authorization_code":
                return await self._handle_authorization_code_grant(form_data, client_id)

            # Handle refresh_token grant
            elif grant_type == "refresh_token":
                return await self._handle_refresh_token_grant(form_data, client_id)

            else:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "unsupported_grant_type",
                        "error_description": f"Grant type '{grant_type}' is not supported"
                    }
                )

        except Exception as e:
            logger.error(f"Token endpoint error: {e}")
            return JSONResponse(
                status_code=500,
                content={
                    "error": "server_error",
                    "error_description": str(e)
                }
            )

    async def _handle_authorization_code_grant(self, form_data, client_id: str) -> JSONResponse:
        """Handle authorization_code grant type."""
        code = form_data.get("code")
        redirect_uri = form_data.get("redirect_uri")
        code_verifier = form_data.get("code_verifier")

        if not code or not redirect_uri:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "invalid_request",
                    "error_description": "Missing code or redirect_uri"
                }
            )

        # Get authorization code
        code_data = self.storage.get_authorization_code(code)
        if not code_data:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "invalid_grant",
                    "error_description": "Invalid, expired, or used authorization code"
                }
            )

        # Validate client_id matches
        if code_data["client_id"] != client_id:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "invalid_grant",
                    "error_description": "Authorization code was issued to different client"
                }
            )

        # Validate redirect_uri matches
        if code_data["redirect_uri"] != redirect_uri:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "invalid_grant",
                    "error_description": "redirect_uri does not match authorization request"
                }
            )

        # Verify PKCE if present
        if code_data.get("code_challenge"):
            if not code_verifier:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "invalid_request",
                        "error_description": "code_verifier is required for PKCE"
                    }
                )

            if not self.verify_pkce_challenge(
                code_verifier,
                code_data["code_challenge"],
                code_data["code_challenge_method"]
            ):
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "invalid_grant",
                        "error_description": "PKCE validation failed"
                    }
                )

        # Mark code as used
        self.storage.mark_code_used(code)

        # Create access token (JWT)
        access_token = self.create_jwt_token(
            user_id=code_data["user_id"],
            client_id=client_id,
            scope=code_data["scope"],
            expires_in=3600  # 1 hour
        )

        # Create refresh token
        refresh_token = self.storage.create_refresh_token(
            client_id=client_id,
            user_id=code_data["user_id"],
            scope=code_data["scope"]
        )

        logger.info(f"Token issued for client: {client_id}, scope: {code_data['scope']}")

        # RFC 6749 token response
        return JSONResponse(
            content={
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": 3600,
                "refresh_token": refresh_token,
                "scope": code_data["scope"]
            }
        )

    async def _handle_refresh_token_grant(self, form_data, client_id: str) -> JSONResponse:
        """Handle refresh_token grant type."""
        refresh_token = form_data.get("refresh_token")

        if not refresh_token:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "invalid_request",
                    "error_description": "Missing refresh_token"
                }
            )

        # Get refresh token data
        token_data = self.storage.get_refresh_token(refresh_token)
        if not token_data:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "invalid_grant",
                    "error_description": "Invalid or expired refresh token"
                }
            )

        # Validate client_id matches
        if token_data["client_id"] != client_id:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "invalid_grant",
                    "error_description": "Refresh token was issued to different client"
                }
            )

        # Rotate refresh token (best practice)
        new_refresh_token = self.storage.rotate_refresh_token(refresh_token)

        # Create new access token
        access_token = self.create_jwt_token(
            user_id=token_data["user_id"],
            client_id=client_id,
            scope=token_data["scope"],
            expires_in=3600
        )

        logger.info(f"Refreshed tokens for client: {client_id}")

        # Token response
        return JSONResponse(
            content={
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": 3600,
                "refresh_token": new_refresh_token,
                "scope": token_data["scope"]
            }
        )

    # ==================== OAuth Discovery (Optional but recommended) ====================

    async def authorization_server_metadata(self, request: Request) -> JSONResponse:
        """
        OAuth Authorization Server Metadata (RFC 8414).

        GET /.well-known/oauth-authorization-server

        Returns discovery document for OAuth clients.
        """
        logger.info(f"OAuth discovery request from {request.client.host if request.client else 'unknown'}")
        base_url = self.get_base_url_from_request(request)
        issuer = self.get_issuer(request)

        return JSONResponse(
            content={
                "issuer": issuer,
                "authorization_endpoint": f"{base_url}/authorize",
                "token_endpoint": f"{base_url}/token",
                "registration_endpoint": f"{base_url}/register",
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "response_types_supported": ["code"],
                "code_challenge_methods_supported": ["S256", "plain"],
                "token_endpoint_auth_methods_supported": ["client_secret_post"],
                "scopes_supported": ["kx-hub:read"],
                "service_documentation": "https://github.com/chrismmuc/kx-hub"
            }
        )

    async def oauth_protected_resource_metadata(self, request: Request) -> JSONResponse:
        """
        OAuth Protected Resource Metadata (RFC 9728).

        GET /.well-known/oauth-protected-resource

        Returns metadata about this protected resource (MCP server)
        and how clients can discover the authorization server.
        """
        base_url = self.get_base_url_from_request(request)
        issuer = self.get_issuer(request)

        return JSONResponse(
            content={
                "resource": base_url,
                "authorization_servers": [issuer],
                "bearer_methods_supported": ["header"],
                "resource_documentation": "https://github.com/chrismmuc/kx-hub",
                "scopes_supported": ["kx-hub:read"]
            }
        )
