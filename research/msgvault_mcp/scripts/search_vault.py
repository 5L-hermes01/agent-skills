import os
import sys
import json
import argparse
import urllib.request
import urllib.error
import ssl

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

def call_mcp_tool(url, password, tool_name, arguments, insecure=False):
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError(f"Invalid URL scheme: {url}")

    from urllib.parse import urlparse
    parsed = urlparse(url)
    if password and parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1") and not insecure:
        raise ValueError("Unencrypted transmission: credentials cannot be sent over HTTP to a remote host. Use HTTPS or pass --insecure.")

    # Setup SSL Context based on --insecure CLI argument
    if insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    else:
        ctx = ssl.create_default_context()
    
    headers = {
        "Content-Type": "application/json",
        "MCP-Protocol-Version": "2025-06-18",
        "User-Agent": "MsgVault-MCP-Client-Python"
    }
    if password:
        # Basic auth format or bearer token
        import base64
        if password.startswith("Bearer "):
            headers["Authorization"] = password
        else:
            auth_str = f"njl:{password}"
            headers["Authorization"] = "Basic " + base64.b64encode(auth_str.encode()).decode()
            
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }
    
    # Initialize session
    init_payload = {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "msgvault-cli", "version": "1.0"}
        }
    }
    
    try:
        # Initialize
        req = urllib.request.Request(url, data=json.dumps(init_payload).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:  # nosec B310
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
        with urllib.request.urlopen(req_notif, context=ctx, timeout=15) as r_notif:  # nosec B310
            r_notif.read()
            
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:  # nosec B310
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
    parser = argparse.ArgumentParser(description="Search emails in MsgVault via MCP.")
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--limit", type=int, default=5, help="Max results")
    parser.add_argument("--insecure", action="store_true", help="Skip TLS certificate verification (unsafe)")
    
    args = parser.parse_args()
    
    # Load .env locally if present
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    env_path = os.path.join(project_root, ".env")
    if os.path.exists(env_path):
        from dotenv import load_dotenv
        load_dotenv(env_path)
        
    url = os.getenv("MSGVAULT_URL")
    password = os.getenv("MSGVAULT_PASSWORD")
    
    if not url:
        print("[-] Error: MSGVAULT_URL must be defined in environment or .env file.", file=sys.stderr)
        sys.exit(1)
        
    if not password:
        print("[-] Error: MSGVAULT_PASSWORD must be defined in environment or .env file.", file=sys.stderr)
        sys.exit(1)
        
    print(f"[+] Searching MsgVault at {url}...")
    result = call_mcp_tool(url, password, "search_messages", {"query": args.query, "limit": args.limit}, insecure=args.insecure)
    
    content = result.get("content", [])
    if content:
        text_data = content[0].get("text", "[]")
        try:
            messages = json.loads(text_data)
            if messages is None:
                messages = []
            print(f"[+] Found {len(messages)} messages:")
            for m in messages:
                print(f"\n- From: {m.get('from_email', m.get('from', ''))}")
                print(f"  Subject: {m.get('subject', '')}")
                print(f"  Snippet: {m.get('snippet', '')}")
        except Exception as e:
            print(f"[-] Failed to parse message JSON: {e}", file=sys.stderr)
            print(text_data, file=sys.stderr)
            sys.exit(1)
    else:
        print("[-] No content returned from MsgVault.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
