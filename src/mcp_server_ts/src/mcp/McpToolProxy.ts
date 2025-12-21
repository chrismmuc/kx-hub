/**
 * MCP Tool Proxy - Forwards tool calls to Python backend API.
 */

import fetch from 'node-fetch';

export class McpToolProxy {
  constructor(private pythonApiUrl: string) {
    console.log(`Tool proxy initialized with Python API: ${pythonApiUrl}`);
  }

  async callTool(toolName: string, args: Record<string, any>): Promise<any> {
    const endpoint = `${this.pythonApiUrl}/tools/${toolName}`;
    console.log(`Calling Python tool: ${toolName} at ${endpoint}`);
    console.log('Arguments:', JSON.stringify(args, null, 2));

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(args),
      });

      if (!response.ok) {
        const errorText = await response.text();
        console.error(`Tool call failed: ${response.status} ${response.statusText}`);
        console.error('Error response:', errorText);

        return {
          content: [
            {
              type: 'text',
              text: `Error calling tool ${toolName}: ${response.status} ${response.statusText}\n${errorText}`
            }
          ],
          isError: true
        };
      }

      const result = await response.json();
      console.log(`Tool ${toolName} executed successfully`);

      // Convert Python tool result to MCP format
      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify(result, null, 2)
          }
        ]
      };
    } catch (error) {
      console.error(`Error calling tool ${toolName}:`, error);

      return {
        content: [
          {
            type: 'text',
            text: `Error calling tool ${toolName}: ${error instanceof Error ? error.message : String(error)}`
          }
        ],
        isError: true
      };
    }
  }
}
