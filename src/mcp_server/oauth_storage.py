"""
OAuth 2.1 Storage Layer for Dynamic Client Registration and Token Management.

Manages OAuth clients, authorization codes, access tokens, and refresh tokens
in Firestore for Claude.ai Mobile and Web access.
"""

import os
import uuid
import secrets
import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from google.cloud import firestore

import logging

logger = logging.getLogger(__name__)


class OAuthStorage:
    """Firestore storage for OAuth 2.1 clients and tokens."""

    def __init__(self):
        """Initialize Firestore client."""
        self.db = firestore.Client(
            project=os.getenv("GCP_PROJECT"),
            database=os.getenv("FIRESTORE_DATABASE", "(default)")
        )
        self.clients_collection = "oauth_clients"
        self.tokens_collection = "oauth_tokens"

    # ==================== Client Management ====================

    def register_client(
        self,
        redirect_uris: List[str],
        client_name: str,
        grant_types: List[str] = None,
        response_types: List[str] = None,
        scope: str = None
    ) -> Dict[str, Any]:
        """
        Register a new OAuth client (RFC 7591).

        Args:
            redirect_uris: List of authorized redirect URIs
            client_name: Human-readable client name
            grant_types: Supported grant types (default: authorization_code, refresh_token)
            response_types: Supported response types (default: code)
            scope: Requested scope (optional)

        Returns:
            Client registration response with client_id and client_secret
        """
        # Generate client credentials
        client_id = str(uuid.uuid4())
        client_secret = secrets.token_urlsafe(32)
        client_secret_hash = bcrypt.hashpw(client_secret.encode(), bcrypt.gensalt()).decode()

        # Set defaults
        if grant_types is None:
            grant_types = ["authorization_code", "refresh_token"]
        if response_types is None:
            response_types = ["code"]

        # Create client document
        client_doc = {
            "client_id": client_id,
            "client_secret_hash": client_secret_hash,
            "client_name": client_name,
            "redirect_uris": redirect_uris,
            "grant_types": grant_types,
            "response_types": response_types,
            "scope": scope or "",
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP
        }

        # Store in Firestore
        self.db.collection(self.clients_collection).document(client_id).set(client_doc)

        logger.info(f"Registered OAuth client: {client_name} (ID: {client_id})")

        # Return registration response (RFC 7591)
        return {
            "client_id": client_id,
            "client_secret": client_secret,  # Only returned once!
            "client_name": client_name,
            "redirect_uris": redirect_uris,
            "grant_types": grant_types,
            "response_types": response_types,
            "token_endpoint_auth_method": "client_secret_post"
        }

    def get_client(self, client_id: str) -> Optional[Dict[str, Any]]:
        """
        Get client by ID.

        Args:
            client_id: Client identifier

        Returns:
            Client document or None if not found
        """
        doc = self.db.collection(self.clients_collection).document(client_id).get()
        if doc.exists:
            return doc.to_dict()
        return None

    def validate_client_secret(self, client_id: str, client_secret: str) -> bool:
        """
        Validate client secret.

        Args:
            client_id: Client identifier
            client_secret: Client secret to validate

        Returns:
            True if secret is valid
        """
        client = self.get_client(client_id)
        if not client:
            return False

        client_secret_hash = client.get("client_secret_hash", "")
        return bcrypt.checkpw(client_secret.encode(), client_secret_hash.encode())

    def validate_redirect_uri(self, client_id: str, redirect_uri: str) -> bool:
        """
        Validate redirect URI against registered URIs.

        Args:
            client_id: Client identifier
            redirect_uri: Redirect URI to validate

        Returns:
            True if URI is registered for this client
        """
        client = self.get_client(client_id)
        if not client:
            return False

        return redirect_uri in client.get("redirect_uris", [])

    # ==================== Authorization Code Management ====================

    def create_authorization_code(
        self,
        client_id: str,
        redirect_uri: str,
        scope: str,
        user_id: str,
        code_challenge: Optional[str] = None,
        code_challenge_method: Optional[str] = None
    ) -> str:
        """
        Create an authorization code.

        Args:
            client_id: Client identifier
            redirect_uri: Redirect URI for this flow
            scope: Requested scope
            user_id: Authenticated user identifier
            code_challenge: PKCE code challenge (optional)
            code_challenge_method: PKCE challenge method (optional)

        Returns:
            Authorization code
        """
        code = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)  # 10 min expiry

        code_doc = {
            "code": code,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "user_id": user_id,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "used": False,
            "created_at": firestore.SERVER_TIMESTAMP,
            "expires_at": expires_at
        }

        self.db.collection(self.tokens_collection).document(f"code_{code}").set(code_doc)

        logger.info(f"Created authorization code for client: {client_id}")
        return code

    def get_authorization_code(self, code: str) -> Optional[Dict[str, Any]]:
        """
        Get authorization code data.

        Args:
            code: Authorization code

        Returns:
            Code document or None if not found/expired/used
        """
        doc = self.db.collection(self.tokens_collection).document(f"code_{code}").get()
        if not doc.exists:
            return None

        code_data = doc.to_dict()

        # Check if used
        if code_data.get("used"):
            logger.warning(f"Authorization code already used: {code}")
            return None

        # Check if expired
        if datetime.now(timezone.utc) > code_data.get("expires_at"):
            logger.warning(f"Authorization code expired: {code}")
            return None

        return code_data

    def mark_code_used(self, code: str):
        """Mark authorization code as used (one-time use)."""
        self.db.collection(self.tokens_collection).document(f"code_{code}").update({"used": True})

    # ==================== Access Token Management ====================

    def create_refresh_token(
        self,
        client_id: str,
        user_id: str,
        scope: str
    ) -> str:
        """
        Create a refresh token.

        Args:
            client_id: Client identifier
            user_id: User identifier
            scope: Token scope

        Returns:
            Refresh token
        """
        refresh_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)  # 30 day expiry

        token_doc = {
            "refresh_token": refresh_token,
            "client_id": client_id,
            "user_id": user_id,
            "scope": scope,
            "used": False,
            "revoked": False,
            "created_at": firestore.SERVER_TIMESTAMP,
            "expires_at": expires_at
        }

        self.db.collection(self.tokens_collection).document(f"refresh_{refresh_token}").set(token_doc)

        logger.info(f"Created refresh token for user: {user_id}")
        return refresh_token

    def get_refresh_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """
        Get refresh token data.

        Args:
            refresh_token: Refresh token

        Returns:
            Token document or None if not found/expired/revoked
        """
        doc = self.db.collection(self.tokens_collection).document(f"refresh_{refresh_token}").get()
        if not doc.exists:
            return None

        token_data = doc.to_dict()

        # Check if revoked
        if token_data.get("revoked"):
            logger.warning(f"Refresh token revoked: {refresh_token}")
            return None

        # Check if expired
        if datetime.now(timezone.utc) > token_data.get("expires_at"):
            logger.warning(f"Refresh token expired: {refresh_token}")
            return None

        return token_data

    def rotate_refresh_token(self, old_refresh_token: str) -> str:
        """
        Rotate refresh token (revoke old, create new).

        Args:
            old_refresh_token: Old refresh token to revoke

        Returns:
            New refresh token
        """
        old_token_data = self.get_refresh_token(old_refresh_token)
        if not old_token_data:
            raise ValueError("Invalid refresh token")

        # Revoke old token
        self.db.collection(self.tokens_collection).document(f"refresh_{old_refresh_token}").update({"revoked": True})

        # Create new token
        return self.create_refresh_token(
            client_id=old_token_data["client_id"],
            user_id=old_token_data["user_id"],
            scope=old_token_data["scope"]
        )

    # ==================== Cleanup ====================

    def cleanup_expired_tokens(self):
        """Delete expired authorization codes and refresh tokens."""
        now = datetime.now(timezone.utc)

        # Cleanup expired codes
        expired_codes = self.db.collection(self.tokens_collection)\
            .where("expires_at", "<", now)\
            .where("__name__", ">=", "code_")\
            .where("__name__", "<", "code_~")\
            .stream()

        deleted_count = 0
        for doc in expired_codes:
            doc.reference.delete()
            deleted_count += 1

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} expired tokens")
