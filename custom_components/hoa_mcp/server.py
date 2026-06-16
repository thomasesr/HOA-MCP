"""MCP SSE server — runs inside Home Assistant's aiohttp HTTP server."""

import asyncio
import json
import logging
import uuid

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .tools import call_tool, get_all_tools

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "hoa-mcp", "version": "1.0.0"}


class McpServer:
    """Holds per-entry config and active SSE sessions."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
        self.entry = entry
        self._sessions: dict[str, asyncio.Queue] = {}

    def new_session(self) -> tuple[str, asyncio.Queue]:
        sid = str(uuid.uuid4())
        q: asyncio.Queue = asyncio.Queue()
        self._sessions[sid] = q
        return sid, q

    def remove_session(self, sid: str) -> None:
        self._sessions.pop(sid, None)

    async def dispatch(self, msg: dict, sid: str) -> None:
        """Parse one JSON-RPC message and send the response into the SSE queue."""
        method = msg.get("method", "")
        msg_id = msg.get("id")
        params = msg.get("params") or {}

        # Notifications never get a response
        if method.startswith("notifications/"):
            return

        try:
            if method == "initialize":
                result = {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": SERVER_INFO,
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": get_all_tools()}
            elif method == "tools/call":
                name = params.get("name", "")
                arguments = params.get("arguments") or {}
                content = await call_tool(name, arguments, self.hass, self.entry)
                result = {
                    "content": [
                        {"type": "text", "text": json.dumps(content, ensure_ascii=False)}
                    ]
                }
            else:
                await self._send(sid, msg_id, error={"code": -32601, "message": f"Method not found: {method}"})
                return
        except Exception as exc:
            logger.exception("Tool error [%s]", method)
            await self._send(sid, msg_id, error={"code": -32603, "message": str(exc)})
            return

        if msg_id is not None:
            await self._send(sid, msg_id, result=result)

    async def _send(self, sid: str, msg_id, *, result=None, error=None) -> None:
        q = self._sessions.get(sid)
        if q is None:
            return
        payload: dict = {"jsonrpc": "2.0", "id": msg_id}
        if error is not None:
            payload["error"] = error
        else:
            payload["result"] = result
        await q.put(payload)


class McpSseView(HomeAssistantView):
    """GET /hoa_mcp/sse — opens an SSE stream for an MCP client."""

    url = "/hoa_mcp/sse"
    name = "hoa_mcp:sse"
    cors_allowed = True
    requires_auth = False

    def __init__(self, server_ref: dict) -> None:
        # server_ref is a mutable dict {"server": McpServer} so reloads update it
        self._ref = server_ref

    async def get(self, request: web.Request) -> web.StreamResponse:
        server: McpServer = self._ref["server"]
        sid, queue = server.new_session()

        response = web.StreamResponse(
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
        await response.prepare(request)

        # MCP SSE protocol: first event tells the client where to POST messages
        endpoint = f"/hoa_mcp/messages?session_id={sid}"
        await response.write(f"event: endpoint\ndata: {endpoint}\n\n".encode())

        try:
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=25)
                    data = json.dumps(msg, ensure_ascii=False)
                    await response.write(f"event: message\ndata: {data}\n\n".encode())
                except asyncio.TimeoutError:
                    await response.write(b": keepalive\n\n")
        except (asyncio.CancelledError, ConnectionResetError):
            pass
        finally:
            server.remove_session(sid)

        return response


class McpMessagesView(HomeAssistantView):
    """POST /hoa_mcp/messages — receives JSON-RPC from the MCP client."""

    url = "/hoa_mcp/messages"
    name = "hoa_mcp:messages"
    cors_allowed = True
    requires_auth = False

    def __init__(self, server_ref: dict) -> None:
        self._ref = server_ref

    async def post(self, request: web.Request) -> web.Response:
        server: McpServer = self._ref["server"]
        sid = request.query.get("session_id", "")

        if sid not in server._sessions:
            return web.Response(status=404, text="Unknown session")

        try:
            body = await request.json()
        except Exception:
            return web.Response(status=400, text="Invalid JSON")

        asyncio.create_task(server.dispatch(body, sid))
        return web.Response(status=202)
