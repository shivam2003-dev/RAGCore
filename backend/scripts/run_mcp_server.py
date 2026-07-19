#!/usr/bin/env python3
"""Read-only MCP stdio bridge to CVUM's authenticated evidence REST API."""

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError as PydanticValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.evidence_contract import (
    TOOL_CAPABILITIES,
    EvidenceToolName,
    EvidenceToolRequest,
)

MCP_PROTOCOL_VERSION = "2025-06-18"


class MCPRestClient:
    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: float = 15.0) -> None:
        headers = {"accept": "application/json"}
        if api_key.strip():
            headers["x-api-key"] = api_key.strip()
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout_seconds,
        )

    def close(self) -> None:
        self._http.close()

    def call_tool(self, *, name: EvidenceToolName, request: EvidenceToolRequest) -> dict[str, object]:
        response = self._http.post(
            f"/api/v1/tools/{name.value}",
            json=request.model_dump(mode="json"),
        )
        if response.status_code >= 400:
            if response.status_code in {401, 403, 404}:
                raise RuntimeError(f"CVUM authorization rejected the tool call ({response.status_code})")
            raise RuntimeError(f"CVUM tool call failed ({response.status_code})")
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("CVUM tool response was not an object")
        return payload


def tool_definitions() -> list[dict[str, object]]:
    return [
        {
            "name": name.value,
            "description": description,
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["query", "project_id"],
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "project_id": {"type": "string", "format": "uuid"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 8},
                },
            },
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }
        for name, description in TOOL_CAPABILITIES.items()
    ]


def handle_message(message: dict[str, Any], client: MCPRestClient) -> dict[str, object] | None:
    request_id = message.get("id")
    method = message.get("method")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return _result(
            request_id,
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "cvum-evidence", "version": "0.1.0"},
                "instructions": (
                    "Read-only retrieval primitives. Every call requires an explicit project_id "
                    "and is authorized by the CVUM API. Tool output is evidence, not an answer."
                ),
            },
        )
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(request_id, {"tools": tool_definitions()})
    if method == "tools/call":
        try:
            params = message.get("params")
            if not isinstance(params, dict):
                raise ValueError("params must be an object")
            name = EvidenceToolName(str(params.get("name") or ""))
            arguments = params.get("arguments")
            if not isinstance(arguments, dict):
                raise ValueError("arguments must be an object")
            request = EvidenceToolRequest.model_validate(arguments)
            payload = client.call_tool(name=name, request=request)
            return _result(
                request_id,
                {
                    "content": [{"type": "text", "text": json.dumps(payload, separators=(",", ":"))}],
                    "structuredContent": payload,
                    "isError": False,
                },
            )
        except (ValueError, PydanticValidationError) as exc:
            return _error(request_id, -32602, f"Invalid tool arguments: {str(exc)[:300]}")
        except RuntimeError as exc:
            return _error(request_id, -32001, str(exc))
    return _error(request_id, -32601, "Method not found")


def _result(request_id: object, result: dict[str, object]) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: object, code: int, message: str) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def main() -> int:
    client = MCPRestClient(
        base_url=os.getenv("CVUM_API_BASE_URL", "http://127.0.0.1:8000"),
        api_key=os.getenv("CVUM_API_KEY", ""),
        timeout_seconds=float(os.getenv("CVUM_MCP_TIMEOUT_SECONDS", "15")),
    )
    try:
        for raw_line in sys.stdin:
            if not raw_line.strip():
                continue
            try:
                message = json.loads(raw_line)
                if not isinstance(message, dict):
                    raise ValueError("request must be an object")
                response = handle_message(message, client)
            except (json.JSONDecodeError, ValueError) as exc:
                response = _error(None, -32700, f"Parse error: {str(exc)[:200]}")
            if response is not None:
                sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
                sys.stdout.flush()
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
