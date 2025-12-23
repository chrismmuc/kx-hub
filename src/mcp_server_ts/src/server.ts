/**
 * Main MCP server with SSE transport and OAuth authentication.
 * This server handles:
 * - SSE transport for MCP protocol
 * - OAuth token validation
 * - Proxying tool calls to Python backend
 */

import express, { Application } from 'express';
import { SseController } from './controllers/SseController';
import { authMiddleware } from './middlewares/AuthMiddleware';

const app: Application = express();
const port = process.env.PORT || 8080;

// Trust proxy (Cloud Run terminates SSL at load balancer)
// This ensures req.protocol returns 'https' based on X-Forwarded-Proto header
app.set('trust proxy', 1);

// Required environment variables
const PYTHON_TOOLS_API_URL = process.env.PYTHON_TOOLS_API_URL;
const OAUTH_LAMBDA_URL = process.env.OAUTH_LAMBDA_URL;

if (!PYTHON_TOOLS_API_URL) {
  console.error('Missing required environment variable: PYTHON_TOOLS_API_URL');
  process.exit(1);
}

if (!OAUTH_LAMBDA_URL) {
  console.error('Missing required environment variable: OAUTH_LAMBDA_URL');
  process.exit(1);
}

// Middleware - NO body parsing for SSE /messages endpoint!
// SSE transport breaks if we parse the body with express.json()
app.use((req, res, next) => {
  if (req.path === '/messages') {
    // Skip all body parsing for SSE - handlePostMessage does it internally
    next();
  } else {
    express.json()(req, res, next);
  }
});
app.use(express.urlencoded({ extended: true }));

// Initialize SSE controller
const sseController = new SseController(PYTHON_TOOLS_API_URL);

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    service: 'kx-hub-mcp-server',
    pythonApiUrl: PYTHON_TOOLS_API_URL
  });
});

// OAuth endpoints - proxy to Lambda
app.get('/.well-known/oauth-authorization-server', async (req, res) => {
  try {
    const fetch = (await import('node-fetch')).default;
    const response = await fetch(`${OAUTH_LAMBDA_URL}/.well-known/oauth-authorization-server`);
    const data = await response.json();
    res.json(data);
  } catch (error) {
    console.error('Error proxying OAuth metadata:', error);
    res.status(500).json({ error: 'Failed to fetch OAuth metadata' });
  }
});

// OAuth Protected Resource Metadata (RFC 9728)
app.get('/.well-known/oauth-protected-resource', async (req, res) => {
  const baseUrl = `${req.protocol}://${req.get('host')}`;
  res.json({
    resource: baseUrl,
    authorization_servers: [OAUTH_LAMBDA_URL],
    bearer_methods_supported: ['header'],
    resource_documentation: 'https://github.com/chrismmuc/kx-hub'
  });
});

app.post('/register', async (req, res) => {
  try {
    const fetch = (await import('node-fetch')).default;
    const response = await fetch(`${OAUTH_LAMBDA_URL}/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req.body)
    });
    const data = await response.json();
    res.status(response.status).json(data);
  } catch (error) {
    console.error('Error proxying client registration:', error);
    res.status(500).json({ error: 'Failed to register client' });
  }
});

// Authorization endpoint - GET for login page, POST for form submission
app.get('/authorize', async (req, res) => {
  try {
    const fetch = (await import('node-fetch')).default;
    const queryString = new URLSearchParams(req.query as any).toString();
    const url = `${OAUTH_LAMBDA_URL}/authorize${queryString ? `?${queryString}` : ''}`;
    const response = await fetch(url);
    const html = await response.text();
    res.status(response.status).send(html);
  } catch (error) {
    console.error('Error proxying authorization GET:', error);
    res.status(500).send('Failed to load authorization page');
  }
});

app.post('/authorize', async (req, res) => {
  try {
    const fetch = (await import('node-fetch')).default;
    const queryString = new URLSearchParams(req.query as any).toString();
    const url = `${OAUTH_LAMBDA_URL}/authorize${queryString ? `?${queryString}` : ''}`;

    // Send form data as application/x-www-form-urlencoded
    const formData = new URLSearchParams(req.body).toString();
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formData,
      redirect: 'manual'  // Don't follow redirects - pass them to browser
    });

    // If OAuth server returns a redirect, forward it to the browser
    if (response.status >= 300 && response.status < 400) {
      const location = response.headers.get('location');
      if (location) {
        return res.redirect(response.status, location);
      }
    }

    const html = await response.text();
    res.status(response.status).send(html);
  } catch (error) {
    console.error('Error proxying authorization POST:', error);
    res.status(500).send('Failed to authorize');
  }
});

app.post('/token', async (req, res) => {
  try {
    const fetch = (await import('node-fetch')).default;
    // OAuth token endpoint uses application/x-www-form-urlencoded
    const formData = new URLSearchParams(req.body).toString();
    const response = await fetch(`${OAUTH_LAMBDA_URL}/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formData
    });
    const data = await response.json();
    res.status(response.status).json(data);
  } catch (error) {
    console.error('Error proxying token exchange:', error);
    res.status(500).json({ error: 'Failed to exchange token' });
  }
});

// SSE endpoint - requires OAuth
app.get('/', authMiddleware, async (req, res) => {
  console.log('SSE connection request from authenticated client');
  await sseController.handleSseConnection(req, res);
});

// Messages endpoint - requires OAuth
app.post('/messages', authMiddleware, async (req, res) => {
  console.log('Messages endpoint called');
  await sseController.handleMessage(req, res);
});

// Start server
app.listen(port, () => {
  console.log(`MCP Server listening on port ${port}`);
  console.log(`Python Tools API: ${PYTHON_TOOLS_API_URL}`);
  console.log(`OAuth Lambda: ${OAUTH_LAMBDA_URL}`);
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('SIGTERM received, shutting down gracefully...');
  sseController.closeAllConnections();
  process.exit(0);
});

process.on('SIGINT', () => {
  console.log('SIGINT received, shutting down gracefully...');
  sseController.closeAllConnections();
  process.exit(0);
});
