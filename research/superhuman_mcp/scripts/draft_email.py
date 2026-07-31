import os
import sys
import json
import argparse
import urllib.request
import urllib.error

def read_jsonrpc_response(r, req_id):
    content_type = r.headers.get("Content-Type", "").lower()
    
    if "text/event-stream" in content_type:
        # Read SSE stream line-by-line to avoid hanging on persistent connections
        for line_bytes in r:
            line = line_bytes.decode("utf-8").strip()
            if line.startswith("data:"):
                data_content = line[5:].strip()
                try:
                    payload = json.loads(data_content)
                    if payload.get("id") == req_id:
                        return payload
                except json.JSONDecodeError:
                    pass
    else:
        # Standard JSON response
        body = r.read().decode("utf-8")
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            print(f"[-] Failed to parse JSON response: {e}", file=sys.stderr)
            sys.exit(1)
            
    print(f"[-] Error: JSON-RPC response with ID {req_id} not found in stream.", file=sys.stderr)
    sys.exit(1)

def call_mcp_tool(url, auth, tool_name, arguments):
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError(f"Invalid URL scheme: {url}")

    from urllib.parse import urlparse
    parsed = urlparse(url)
    if auth and parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Unencrypted transmission: credentials cannot be sent over HTTP to a remote host. Use HTTPS.")

    headers = {
        "Content-Type": "application/json",
        "MCP-Protocol-Version": "2025-06-18",
        "User-Agent": "Superhuman-MCP-Client-Python"
    }
    if auth:
        headers["Authorization"] = auth if auth.startswith("Bearer ") else f"Bearer {auth}"
        
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }
    
    # We must first initialize the SSE/HTTP session
    init_payload = {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "superhuman-cli", "version": "1.0"}
        }
    }
    
    try:
        # Initialize
        req = urllib.request.Request(url, data=json.dumps(init_payload).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:  # nosec B310
            sid = r.headers.get("Mcp-Session-Id")
            init_res = read_jsonrpc_response(r, 0)
            if "error" in init_res:
                print(f"[-] MCP Initialization Error: {init_res['error']}", file=sys.stderr)
                sys.exit(1)
            
        # Call tool
        if sid:
            headers["Mcp-Session-Id"] = sid
            
        # Send notifications/initialized as required by MCP 2025-06-18 spec
        init_notif = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        }
        req_notif = urllib.request.Request(url, data=json.dumps(init_notif).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req_notif, timeout=15) as r_notif:  # nosec B310
            r_notif.read()
            
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:  # nosec B310
            res = read_jsonrpc_response(r, 1)
            if "error" in res:
                print(f"[-] MCP Error: {res['error']}", file=sys.stderr)
                sys.exit(1)
            return res.get("result", {})
            
    except urllib.error.HTTPError as e:
        print(f"[-] HTTP Error {e.code}: {e.read().decode()}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[-] Connection Error: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Create or update an email draft via Superhuman Mail MCP.")
    parser.add_argument("--to", required=True, help="Recipient email address")
    parser.add_argument("--subject", help="Subject line")
    parser.add_argument("--body", help="HTML body content (direct write)")
    parser.add_argument("--instructions", help="AI instructions for the email draft")
    
    args = parser.parse_args()
    
    # Load .env locally if present
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    env_path = os.path.join(project_root, ".env")
    if os.path.exists(env_path):
        from dotenv import load_dotenv
        load_dotenv(env_path)
        
    url = os.getenv("SUPERHUMAN_URL")
    auth = os.getenv("SUPERHUMAN_AUTH")
    
    if not url:
        print("[-] Error: SUPERHUMAN_URL must be defined in environment or .env file.", file=sys.stderr)
        sys.exit(1)
        
    tool_args = {
        "type": "new",
        "to": [args.to]
    }
    if args.subject:
        tool_args["subject"] = args.subject
    if args.body:
        tool_args["body"] = args.body
    if args.instructions:
        tool_args["instructions"] = args.instructions
        
    if not args.body and not args.instructions:
        print("[-] Error: Either --body or --instructions must be provided.", file=sys.stderr)
        sys.exit(1)
        
    print(f"[+] Creating email draft to '{args.to}' via Superhuman MCP...")
    result = call_mcp_tool(url, auth, "create_or_update_draft", tool_args)
    print("[+] Successfully created draft!")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
