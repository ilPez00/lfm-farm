#!/usr/bin/env python3
"""
LFM Router — Tool calling pair router
Routes tool execution to LFM2.5 (fast) and reasoning to the smart model (brain).
Exposes a single OpenAI-compatible endpoint on :8080.
"""

import argparse
import json
import requests
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

TOOL_SERVER = "http://127.0.0.1:8081"
BRAIN_SERVER = "http://127.0.0.1:8082"

class RouterHandler(BaseHTTPRequestHandler):
    """Routes /v1/chat/completions to the right backend."""
    
    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return
        
        # Determine if this is a tool call or reasoning
        messages = data.get("messages", [])
        tools = data.get("tools", [])
        
        # Heuristic: if last message is a tool result, send to brain for reasoning
        # If we have tools and no tool results yet, send to LFM2.5 for tool execution
        last_msg = messages[-1] if messages else {}
        has_tool_results = any(m.get("role") == "tool" for m in messages[-3:])
        has_tools = bool(tools)
        
        if has_tool_results:
            # Tool results present → brain does reasoning
            target = BRAIN_SERVER
            label = "brain"
        elif has_tools and last_msg.get("role") == "user":
            # User message with tools available → LFM2.5 decides + executes
            target = TOOL_SERVER
            label = "tool"
        else:
            # Default: brain handles it
            target = BRAIN_SERVER
            label = "brain"
        
        # Forward request
        try:
            resp = requests.post(
                f"{target}/v1/chat/completions",
                json=data,
                headers={"Content-Type": "application/json"},
                stream=data.get("stream", False),
                timeout=120
            )
            
            self.send_response(resp.status_code)
            for k, v in resp.headers.items():
                if k.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(k, v)
            self.send_header("X-LFM-Route", label)
            self.end_headers()
            
            if data.get("stream", False):
                for chunk in resp.iter_content(chunk_size=8192):
                    self.wfile.write(chunk)
            else:
                self.wfile.write(resp.content)
                
        except Exception as e:
            self.send_error(502, f"Backend error: {e}")
    
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok",
                "tool_server": TOOL_SERVER,
                "brain_server": BRAIN_SERVER
            }).encode())
        else:
            self.send_error(404)
    
    def log_message(self, format, *args):
        """Suppress default logging to keep output clean."""
        pass

def main():
    global TOOL_SERVER, BRAIN_SERVER
    
    parser = argparse.ArgumentParser(description="LFM Tool Calling Router")
    parser.add_argument("--listen", default="0.0.0.0:8080", help="Listen address")
    parser.add_argument("--tool-server", default=TOOL_SERVER, help="LFM2.5 tool server")
    parser.add_argument("--brain-server", default=BRAIN_SERVER, help="Smart model server")
    args = parser.parse_args()
    
    TOOL_SERVER = args.tool_server
    BRAIN_SERVER = args.brain_server
    
    host, port = args.listen.split(":")
    port = int(port)
    
    print(f"[lfm_router] listening on {args.listen}")
    print(f"[lfm_router] tool server: {TOOL_SERVER}")
    print(f"[lfm_router] brain server: {BRAIN_SERVER}")
    
    server = HTTPServer((host, port), RouterHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[lfm_router] shutting down")
        server.shutdown()

if __name__ == "__main__":
    main()
