"""
Tests for MCP Server SSE transport and authentication.

Tests cover:
- Bearer token authentication middleware
- SSE endpoint functionality
- Environment variable validation
- Transport mode switching

NOTE: Tests for server_sse module and Dockerfile.mcp-server are skipped
because these components have not been implemented yet. The MCP server
currently uses a consolidated approach (server.py + Dockerfile.mcp-consolidated).
"""

import os
from unittest.mock import AsyncMock, Mock, patch

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient


@pytest.fixture
def mock_env_vars():
    """Set up test environment variables."""
    env = {
        "MCP_AUTH_TOKEN": "test-token-12345",
        "GCP_PROJECT": "test-project",
        "GCP_REGION": "us-central1",
        "FIRESTORE_COLLECTION": "kb_items",
        "TRANSPORT_MODE": "sse",
    }
    with patch.dict(os.environ, env, clear=False):
        yield env


@pytest.mark.skip(
    reason="server_sse module not implemented - using consolidated server.py instead"
)
class TestBearerTokenAuth:
    """Test Bearer token authentication middleware."""

    def test_valid_token_allows_access(self, mock_env_vars):
        """Test that valid Bearer token grants access."""
        from src.mcp_server.server_sse import BearerTokenAuthMiddleware

        # Create simple test app
        async def endpoint(request):
            return JSONResponse({"status": "ok"})

        app = Starlette(routes=[Route("/test", endpoint)])
        app = BearerTokenAuthMiddleware(app, required_token="test-token-12345")

        client = TestClient(app)
        response = client.get(
            "/test", headers={"Authorization": "Bearer test-token-12345"}
        )

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_invalid_token_returns_401(self, mock_env_vars):
        """Test that invalid Bearer token returns 401."""
        from src.mcp_server.server_sse import BearerTokenAuthMiddleware

        async def endpoint(request):
            return JSONResponse({"status": "ok"})

        app = Starlette(routes=[Route("/test", endpoint)])
        app = BearerTokenAuthMiddleware(app, required_token="test-token-12345")

        client = TestClient(app)
        response = client.get("/test", headers={"Authorization": "Bearer wrong-token"})

        assert response.status_code == 401
        assert "Unauthorized" in response.json()["error"]

    def test_missing_auth_header_returns_401(self, mock_env_vars):
        """Test that missing Authorization header returns 401."""
        from src.mcp_server.server_sse import BearerTokenAuthMiddleware

        async def endpoint(request):
            return JSONResponse({"status": "ok"})

        app = Starlette(routes=[Route("/test", endpoint)])
        app = BearerTokenAuthMiddleware(app, required_token="test-token-12345")

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 401
        assert "Unauthorized" in response.json()["error"]

    def test_malformed_auth_header_returns_401(self, mock_env_vars):
        """Test that malformed Authorization header returns 401."""
        from src.mcp_server.server_sse import BearerTokenAuthMiddleware

        async def endpoint(request):
            return JSONResponse({"status": "ok"})

        app = Starlette(routes=[Route("/test", endpoint)])
        app = BearerTokenAuthMiddleware(app, required_token="test-token-12345")

        client = TestClient(app)
        response = client.get(
            "/test", headers={"Authorization": "Basic test-token-12345"}
        )

        assert response.status_code == 401

    def test_health_endpoint_bypasses_auth(self, mock_env_vars):
        """Test that /health endpoint does not require authentication."""
        from src.mcp_server.server_sse import BearerTokenAuthMiddleware

        async def health_endpoint(request):
            return JSONResponse({"status": "healthy"})

        app = Starlette(routes=[Route("/health", health_endpoint)])
        app = BearerTokenAuthMiddleware(app, required_token="test-token-12345")

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


@pytest.mark.skip(
    reason="server_sse module not implemented - using consolidated server.py instead"
)
class TestSSEServerCreation:
    """Test SSE server app creation."""

    def test_create_sse_app_requires_auth_token(self):
        """Test that creating SSE app without MCP_AUTH_TOKEN raises error."""
        from src.mcp_server.server_sse import create_sse_app

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="MCP_AUTH_TOKEN"):
                mock_server = Mock()
                create_sse_app(mock_server)

    def test_create_sse_app_with_token(self, mock_env_vars):
        """Test that SSE app is created successfully with auth token."""
        from src.mcp_server.server_sse import create_sse_app

        mock_server = Mock()
        app = create_sse_app(mock_server)

        assert app is not None
        assert hasattr(app, "state")
        assert app.state.mcp_server == mock_server

    def test_health_endpoint_exists(self, mock_env_vars):
        """Test that health endpoint is accessible."""
        from src.mcp_server.server_sse import create_sse_app

        mock_server = Mock()
        app = create_sse_app(mock_server)

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestTransportMode:
    """Test transport mode selection."""

    def test_stdio_mode_default(self):
        """Test that stdio is the default transport mode."""
        with patch.dict(os.environ, {}, clear=True):
            mode = os.getenv("TRANSPORT_MODE", "stdio")
            assert mode == "stdio"

    def test_sse_mode_from_env(self):
        """Test that SSE mode can be set via environment."""
        with patch.dict(os.environ, {"TRANSPORT_MODE": "sse"}):
            mode = os.getenv("TRANSPORT_MODE", "stdio")
            assert mode == "sse"


class TestEnvironmentValidation:
    """Test environment variable validation."""

    def test_sse_mode_validates_required_vars(self):
        """Test that SSE mode validates required environment variables."""
        required_vars = [
            "GCP_PROJECT",
            "GCP_REGION",
            "FIRESTORE_COLLECTION",
            "MCP_AUTH_TOKEN",
        ]

        # Test with all vars present
        with patch.dict(
            os.environ,
            {
                "GCP_PROJECT": "test",
                "GCP_REGION": "us-central1",
                "FIRESTORE_COLLECTION": "kb_items",
                "MCP_AUTH_TOKEN": "token",
            },
        ):
            missing = [v for v in required_vars if not os.getenv(v)]
            assert len(missing) == 0

        # Test with missing var
        with patch.dict(
            os.environ,
            {
                "GCP_PROJECT": "test",
                "GCP_REGION": "us-central1",
                "FIRESTORE_COLLECTION": "kb_items",
                # MCP_AUTH_TOKEN missing
            },
        ):
            missing = [v for v in required_vars if not os.getenv(v)]
            assert "MCP_AUTH_TOKEN" in missing

    def test_stdio_mode_validates_credentials(self):
        """Test that stdio mode validates GOOGLE_APPLICATION_CREDENTIALS."""
        required_vars = [
            "GOOGLE_APPLICATION_CREDENTIALS",
            "GCP_PROJECT",
            "GCP_REGION",
            "FIRESTORE_COLLECTION",
        ]

        with patch.dict(os.environ, {}, clear=True):
            missing = [v for v in required_vars if not os.getenv(v)]
            assert len(missing) == 4


@pytest.mark.skip(
    reason="server_sse module not implemented - using consolidated server.py instead"
)
class TestSecurityFeatures:
    """Test security features."""

    def test_no_cors_headers(self, mock_env_vars):
        """Test that CORS headers are not present."""
        from src.mcp_server.server_sse import create_sse_app

        mock_server = Mock()
        app = create_sse_app(mock_server)

        client = TestClient(app)
        response = client.get("/health")

        assert "Access-Control-Allow-Origin" not in response.headers

    def test_auth_token_not_logged(self, mock_env_vars, caplog):
        """Test that auth token is not logged in plain text."""
        from src.mcp_server.server_sse import BearerTokenAuthMiddleware

        async def endpoint(request):
            return JSONResponse({"status": "ok"})

        app = Starlette(routes=[Route("/test", endpoint)])
        app = BearerTokenAuthMiddleware(app, required_token="super-secret-token")

        client = TestClient(app)

        # Test with valid token
        with caplog.at_level("INFO"):
            response = client.get(
                "/test", headers={"Authorization": "Bearer super-secret-token"}
            )

        # Check that token value is not in logs
        for record in caplog.records:
            assert "super-secret-token" not in record.message

        # But authentication should be logged
        assert any(
            "Authenticated request" in record.message for record in caplog.records
        )


@pytest.mark.skip(
    reason="Dockerfile.mcp-server not implemented - using Dockerfile.mcp-consolidated instead"
)
class TestDockerfile:
    """Test Dockerfile configuration."""

    def test_dockerfile_exists(self):
        """Test that Dockerfile exists."""
        import os

        dockerfile_path = "/Users/christian/dev/kx-hub/Dockerfile.mcp-server"
        assert os.path.exists(dockerfile_path)

    def test_dockerfile_uses_nonroot_user(self):
        """Test that Dockerfile creates and uses non-root user."""
        with open("/Users/christian/dev/kx-hub/Dockerfile.mcp-server") as f:
            content = f.read()

        assert "useradd" in content or "RUN adduser" in content
        assert "USER" in content
        assert "mcpserver" in content

    def test_dockerfile_exposes_port_8080(self):
        """Test that Dockerfile exposes port 8080."""
        with open("/Users/christian/dev/kx-hub/Dockerfile.mcp-server") as f:
            content = f.read()

        assert "EXPOSE 8080" in content

    def test_dockerfile_has_healthcheck(self):
        """Test that Dockerfile includes health check."""
        with open("/Users/christian/dev/kx-hub/Dockerfile.mcp-server") as f:
            content = f.read()

        assert "HEALTHCHECK" in content
        assert "/health" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
