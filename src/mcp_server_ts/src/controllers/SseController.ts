/**
 * SSE Controller - Handles Server-Sent Events connections for MCP protocol.
 * Based on the Medium article pattern: https://loginov-rocks.medium.com/build-remote-mcp-with-authorization-a2f394c669a8
 */

import { Request, Response } from 'express';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { SSEServerTransport } from '@modelcontextprotocol/sdk/server/sse.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import { McpToolProxy } from '../mcp/McpToolProxy';

export class SseController {
  private transportsMap: Map<string, SSEServerTransport> = new Map();
  private mcpServer: Server;
  private toolProxy: McpToolProxy;

  constructor(pythonApiUrl: string) {
    this.toolProxy = new McpToolProxy(pythonApiUrl);
    this.mcpServer = new Server(
      {
        name: 'kx-hub',
        version: '1.0.0',
      },
      {
        capabilities: {
          tools: {},
        },
      }
    );

    this.setupToolHandlers();
  }

  private setupToolHandlers(): void {
    // List tools - returns static list of available tools
    this.mcpServer.setRequestHandler(ListToolsRequestSchema, async () => {
      console.log('Handling ListTools request');
      return {
        tools: [
          {
            name: 'search_kb',
            description: 'Unified knowledge base search with flexible filtering (Story 4.1). Combines semantic search with cluster, metadata, time, and knowledge card filters.',
            inputSchema: {
              type: 'object',
              properties: {
                query: {
                  type: 'string',
                  description: 'Natural language search query'
                },
                filters: {
                  type: 'object',
                  description: 'Optional filters to narrow results'
                },
                limit: {
                  type: 'integer',
                  description: 'Maximum number of results (default 10)',
                  default: 10
                }
              },
              required: ['query']
            }
          },
          {
            name: 'get_chunk',
            description: 'Get full details for a specific chunk including knowledge card and related chunks (Story 4.2). Consolidates get_related_chunks and get_knowledge_card into one call.',
            inputSchema: {
              type: 'object',
              properties: {
                chunk_id: {
                  type: 'string',
                  description: 'Chunk ID to retrieve'
                },
                include_related: {
                  type: 'boolean',
                  description: 'Include related chunks via vector similarity (default true)',
                  default: true
                },
                related_limit: {
                  type: 'integer',
                  description: 'Maximum related chunks to return (default 5, max 20)',
                  default: 5
                }
              },
              required: ['chunk_id']
            }
          },
          {
            name: 'get_recent',
            description: 'Get recent reading activity and chunks (Story 4.3). Consolidates get_recently_added and get_reading_activity into one call.',
            inputSchema: {
              type: 'object',
              properties: {
                limit: {
                  type: 'integer',
                  description: 'Maximum chunks to return (default 10)',
                  default: 10
                },
                period: {
                  type: 'string',
                  description: "Time period (default 'last_7_days')",
                  default: 'last_7_days',
                  enum: ['today', 'yesterday', 'last_3_days', 'last_week', 'last_7_days', 'last_month', 'last_30_days']
                }
              }
            }
          },
          {
            name: 'get_stats',
            description: 'Get knowledge base statistics (total chunks, sources, authors, tags)',
            inputSchema: {
              type: 'object',
              properties: {}
            }
          },
          {
            name: 'list_clusters',
            description: 'List all semantic clusters with metadata',
            inputSchema: {
              type: 'object',
              properties: {}
            }
          },
          {
            name: 'get_cluster',
            description: 'Get cluster details with member chunks and related clusters (Story 4.4). Consolidates get_cluster and get_related_clusters.',
            inputSchema: {
              type: 'object',
              properties: {
                cluster_id: {
                  type: 'string',
                  description: 'Cluster ID to fetch'
                },
                include_members: {
                  type: 'boolean',
                  description: 'Whether to include member chunks (default True)',
                  default: true
                },
                include_related: {
                  type: 'boolean',
                  description: 'Whether to include related clusters (default True)',
                  default: true
                },
                member_limit: {
                  type: 'integer',
                  description: 'Maximum member chunks to return (default 20)',
                  default: 20
                },
                related_limit: {
                  type: 'integer',
                  description: 'Maximum related clusters to return (default 5)',
                  default: 5
                }
              },
              required: ['cluster_id']
            }
          },
          {
            name: 'configure_kb',
            description: 'Unified configuration tool for kx-hub settings (Story 4.5). Consolidates all configuration tools into single entry point.',
            inputSchema: {
              type: 'object',
              properties: {
                action: {
                  type: 'string',
                  description: 'Action to perform',
                  enum: ['show_all', 'show_ranking', 'show_domains', 'show_hot_sites', 'update_ranking', 'update_domains', 'update_hot_sites']
                },
                params: {
                  type: 'object',
                  description: 'Action-specific parameters (optional)'
                }
              },
              required: ['action']
            }
          },
          {
            name: 'search_within_cluster',
            description: 'Semantic search restricted to a specific cluster',
            inputSchema: {
              type: 'object',
              properties: {
                cluster_id: {
                  type: 'string',
                  description: 'Cluster ID to search within'
                },
                query: {
                  type: 'string',
                  description: 'Natural language search query'
                },
                limit: {
                  type: 'integer',
                  description: 'Maximum number of results (default 10)',
                  default: 10
                }
              },
              required: ['cluster_id', 'query']
            }
          },
          {
            name: 'get_reading_recommendations',
            description: 'Get AI-powered reading recommendations based on your KB content. Analyzes recent reads and clusters, searches quality sources, and filters for depth.',
            inputSchema: {
              type: 'object',
              properties: {
                cluster_ids: {
                  type: 'array',
                  items: { type: 'string' },
                  description: "Optional list of cluster IDs to scope recommendations (e.g., ['cluster-28', 'cluster-20'])"
                },
                days: {
                  type: 'integer',
                  description: 'Lookback period for recent reads in days (default 14)',
                  default: 14
                },
                hot_sites: {
                  type: 'string',
                  description: "Optional source category: 'tech', 'tech_de', 'ai', 'devops', 'business', or 'all'",
                  enum: ['tech', 'tech_de', 'ai', 'devops', 'business', 'all']
                },
                include_seen: {
                  type: 'boolean',
                  description: 'Include previously shown recommendations (default false)',
                  default: false
                },
                limit: {
                  type: 'integer',
                  description: 'Maximum recommendations to return (default 10)',
                  default: 10
                },
                mode: {
                  type: 'string',
                  description: "Discovery mode: 'balanced' (default), 'fresh' (recent content), 'deep' (in-depth), 'surprise_me' (high randomization)",
                  default: 'balanced',
                  enum: ['balanced', 'fresh', 'deep', 'surprise_me']
                },
                predictable: {
                  type: 'boolean',
                  description: 'Disable query variation for reproducible results (default false)',
                  default: false
                },
                scope: {
                  type: 'string',
                  description: "Scope for recommendations: 'recent' (recent reads), 'clusters' (top clusters), or 'both' (default)",
                  default: 'both',
                  enum: ['recent', 'clusters', 'both']
                }
              }
            }
          }
        ]
      };
    });

    // Call tool - proxy to Python backend
    this.mcpServer.setRequestHandler(CallToolRequestSchema, async (request) => {
      console.log(`Handling CallTool request: ${request.params.name}`);
      return await this.toolProxy.callTool(request.params.name, request.params.arguments || {});
    });
  }

  /**
   * Handle SSE connection - based on Medium article pattern
   */
  async handleSseConnection(req: Request, res: Response): Promise<void> {
    console.log('Setting up SSE transport...');

    // Important: Don't end the response - SSE keeps it open
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');

    const transport = new SSEServerTransport('/messages', res);
    this.transportsMap.set(transport.sessionId, transport);

    res.on('close', () => {
      console.log(`SSE connection closed for session: ${transport.sessionId}`);
      this.transportsMap.delete(transport.sessionId);
    });

    res.on('error', (error: Error) => {
      console.error(`SSE connection error for session: ${transport.sessionId}`, error);
      this.transportsMap.delete(transport.sessionId);
    });

    console.log(`Connecting MCP server for session: ${transport.sessionId}`);
    await this.mcpServer.connect(transport);
    console.log(`MCP server connected successfully for session: ${transport.sessionId}`);

    // Note: We don't call res.end() - the SSE transport keeps the connection open
  }

  /**
   * Handle incoming messages from client
   */
  async handleMessage(req: Request, res: Response): Promise<void> {
    console.log('handleMessage called, query params:', req.query);
    const sessionId = req.query.sessionId as string;

    if (!sessionId) {
      console.error('Missing sessionId in query parameters');
      res.status(400).json({ error: 'Missing sessionId query parameter' });
      return;
    }

    console.log(`Looking for transport with sessionId: ${sessionId}`);
    console.log(`Active transports: ${Array.from(this.transportsMap.keys()).join(', ')}`);
    const transport = this.transportsMap.get(sessionId);

    if (!transport) {
      console.error(`No transport found for session: ${sessionId}`);
      res.status(404).json({ error: `No transport found for session: ${sessionId}` });
      return;
    }

    console.log(`Transport found for session: ${sessionId}, forwarding message...`);
    console.log(`Message body type: ${typeof req.body}, content: ${JSON.stringify(req.body).substring(0, 200)}`);
    try {
      await transport.handlePostMessage(req, res);
      console.log(`Message handled successfully for session: ${sessionId}`);
    } catch (error) {
      console.error('Error handling message:', error);
      res.status(500).json({ error: 'Failed to handle message' });
    }
  }

  /**
   * Close all active SSE connections
   */
  closeAllConnections(): void {
    console.log(`Closing ${this.transportsMap.size} active SSE connections...`);
    this.transportsMap.forEach((transport) => {
      transport.close();
    });
    this.transportsMap.clear();
  }
}
