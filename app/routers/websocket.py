from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Set
import asyncio
import json

router = APIRouter()

# Store active WebSocket connections
active_connections: Set[WebSocket] = set()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.add(websocket)
    try:
        while True:
            # Keep connection alive, wait for messages (though we don't expect any from client)
            await websocket.receive_text()
    except (WebSocketDisconnect, asyncio.CancelledError):
        active_connections.discard(websocket)

async def broadcast_price_update(symbol: str, price: float):
    """Broadcast a price update to all connected clients"""
    message = json.dumps({
        "type": "price_update",
        "symbol": symbol,
        "price": price
    })

    # Send to all connected clients
    disconnected = set()
    for connection in active_connections:
        try:
            await connection.send_text(message)
        except:
            disconnected.add(connection)

    # Clean up disconnected clients
    for conn in disconnected:
        active_connections.discard(conn)
