#!/usr/bin/env python3
"""
MCP Screenshot Server for Claude Code
Provides screenshot capabilities using gnome-screenshot
"""
import asyncio
import json
import sys
import os
import subprocess
import base64
from datetime import datetime

class ScreenshotMCPServer:
    def __init__(self):
        self.name = "screenshot"
        self.version = "1.0.0"

    async def take_screenshot(self, filename=None, output_name=None):
        """Take a screenshot using gnome-screenshot"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"/tmp/screenshot_{timestamp}.png"

        try:
            # Use gnome-screenshot to take screenshot
            cmd = ["gnome-screenshot", "-f", filename]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)

            # Check if file was created
            if not os.path.exists(filename):
                return {"error": "Screenshot file not created"}

            file_size = os.path.getsize(filename)

            return {
                "success": True,
                "filename": filename,
                "size": file_size,
                "message": f"Screenshot saved to {filename} ({file_size} bytes)"
            }

        except subprocess.CalledProcessError as e:
            return {"error": f"Screenshot command failed: {e.stderr}"}
        except Exception as e:
            return {"error": str(e)}

    async def handle_request(self, request):
        """Handle MCP protocol requests with proper JSON-RPC 2.0 format"""
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")

        # Build the response envelope
        response = {
            "jsonrpc": "2.0",
            "id": request_id
        }

        try:
            if method == "tools/list":
                response["result"] = {
                    "tools": [
                        {
                            "name": "take_screenshot",
                            "description": "Take a screenshot of the entire screen using gnome-screenshot",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "filename": {
                                        "type": "string",
                                        "description": "Optional filename for the screenshot (default: /tmp/screenshot_TIMESTAMP.png)"
                                    },
                                    "output_name": {
                                        "type": "string",
                                        "description": "Optional descriptive name for what's being captured"
                                    }
                                }
                            }
                        }
                    ]
                }

            elif method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments", {})

                if tool_name == "take_screenshot":
                    result = await self.take_screenshot(
                        filename=tool_args.get("filename"),
                        output_name=tool_args.get("output_name")
                    )
                    response["result"] = {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
                else:
                    response["error"] = {"code": -32601, "message": f"Unknown tool: {tool_name}"}

            elif method == "initialize":
                response["result"] = {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {
                        "name": self.name,
                        "version": self.version
                    },
                    "capabilities": {
                        "tools": {}
                    }
                }

            else:
                response["error"] = {"code": -32601, "message": f"Unknown method: {method}"}

        except Exception as e:
            response["error"] = {"code": -32603, "message": str(e)}

        return response

    async def run(self):
        """Run the MCP server using stdio transport"""
        while True:
            try:
                line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
                if not line:
                    break

                request = json.loads(line)
                response = await self.handle_request(request)

                print(json.dumps(response), flush=True)

            except json.JSONDecodeError as e:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error: Invalid JSON"}
                }
                print(json.dumps(error_response), flush=True)
            except Exception as e:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
                }
                print(json.dumps(error_response), flush=True)

if __name__ == "__main__":
    server = ScreenshotMCPServer()
    asyncio.run(server.run())
