"""Client for the Local Business Website Auditor (champ1918/local-business-website-auditor).

Two transports, same result shape:
  1. MCP (primary)  - the Actor is a native MCP tool on mcp.apify.com; Strands' MCPClient
                      connects over streamable HTTP.
  2. REST (fallback)- plain Apify API v2 run-sync call, used when MCP is unavailable
                      so the sentinel keeps working.

Both need APIFY_TOKEN in the environment. The token never appears in code or config.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

ACTOR = "champ1918~local-business-website-auditor"
APIFY_BASE = "https://api.apify.com/v2"


def _token() -> str:
    tok = os.environ.get("APIFY_TOKEN", "")
    if not tok:
        raise RuntimeError(
            "APIFY_TOKEN is not set. Export it before running the sentinel: "
            "export APIFY_TOKEN=... (find it in Apify Console > API & Integrations)"
        )
    return tok


def audit_urls_rest(urls: list[str], timeout_s: int = 120) -> list[dict]:
    """Run the auditor synchronously via the Apify REST API and return dataset rows."""
    payload = json.dumps({
        "startUrls": [{"url": u} for u in urls],
        "maxRequestsPerCrawl": max(10, len(urls) * 2),
    }).encode()

    req = urllib.request.Request(
        f"{APIFY_BASE}/acts/{ACTOR}/run-sync-get-dataset-items?token={_token()}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.time()
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        rows = json.loads(resp.read().decode())
    elapsed = time.time() - started
    for r in rows:
        r["_scan_elapsed_s"] = round(elapsed, 2)
    return rows


def mcp_transport():
    """Streamable-HTTP MCP transport for the Actor, for use with strands MCPClient.

    Usage:
        from strands.tools.mcp import MCPClient
        client = MCPClient(mcp_transport)
        with client:
            tools = client.list_tools_sync()
            agent = Agent(tools=tools, ...)
    """
    from mcp.client.streamable_http import streamablehttp_client
    return streamablehttp_client(
        "https://mcp.apify.com?tools=champ1918/local-business-website-auditor",
        headers={"Authorization": f"Bearer {_token()}"},
    )
