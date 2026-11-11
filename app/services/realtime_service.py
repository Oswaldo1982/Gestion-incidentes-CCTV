import asyncio
import datetime
import json
import logging
from typing import Any, Dict, Optional, Set
from fastapi import Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

logger = logging.getLogger("cctv_realtime")


class RealtimeManager:
    """
    Gestor ligero y no bloqueante de eventos en tiempo real (SSE + WebSockets).
    Utiliza colas acotadas en memoria (maxsize=32) por cliente conectado para evitar
    fugas de memoria o bloqueos en el servidor.
    """

    def __init__(self) -> None:
        self._sse_queues: Set[asyncio.Queue] = set()
        self._websockets: Set[WebSocket] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._version: int = 0

    def bind_loop(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """Asocia el bucle de eventos principal de asyncio para soporte thread-safe."""
        try:
            self._loop = loop or asyncio.get_running_loop()
        except RuntimeError:
            pass

    @property
    def version(self) -> int:
        return self._version

    def notify(self, event_type: str = "data_updated", payload: Optional[Dict[str, Any]] = None) -> None:
        """
        Emite un evento de actualización a todos los clientes conectados (SSE y WebSocket)
        de forma segura entre hilos (thread-safe) y sin bloquear el hilo emisor.
        """
        self._version += 1

        if not self._sse_queues and not self._websockets:
            return

        message: Dict[str, Any] = {
            "version": self._version,
            "event": event_type,
            "timestamp": datetime.datetime.now().isoformat(),
            "payload": payload or {},
        }

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is not None and running_loop.is_running():
            self._dispatch_nowait(message)
        elif self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._dispatch_nowait, message)

    def _dispatch_nowait(self, message: Dict[str, Any]) -> None:
        """Despacha el mensaje en el bucle de eventos sin bloquear."""
        for q in list(self._sse_queues):
            try:
                if q.full():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                q.put_nowait(message)
            except Exception:
                self._sse_queues.discard(q)

        for ws in list(self._websockets):
            asyncio.create_task(self._send_ws_safe(ws, message))

    async def _send_ws_safe(self, ws: WebSocket, message: Dict[str, Any]) -> None:
        try:
            await ws.send_json(message)
        except Exception:
            self._websockets.discard(ws)

    async def sse_stream(self, request: Request):
        """Generador asíncrono para Server-Sent Events (SSE) con limpieza automática."""
        self.bind_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=32)
        self._sse_queues.add(q)

        try:
            init_data = json.dumps({"event": "connected", "version": self._version})
            yield f"retry: 2000\nevent: connected\ndata: {init_data}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15.0)
                    data_str = json.dumps(msg, ensure_ascii=False)
                    yield f"event: update\ndata: {data_str}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.debug(f"SSE stream closed: {exc}")
        finally:
            self._sse_queues.discard(q)

    def create_sse_response(self, request: Request) -> StreamingResponse:
        """Crea la respuesta HTTP StreamingResponse compatible con EventSource."""
        return StreamingResponse(
            self.sse_stream(request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    async def handle_websocket(self, websocket: WebSocket) -> None:
        """Manejador de conexión WebSocket con limpieza garantizada al desconectar."""
        self.bind_loop()
        await websocket.accept()
        self._websockets.add(websocket)
        try:
            await websocket.send_json({"event": "connected", "version": self._version})
            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_json({"event": "pong", "version": self._version})
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            self._websockets.discard(websocket)


realtime_manager = RealtimeManager()

