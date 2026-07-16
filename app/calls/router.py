import json
import uuid

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.calls import session_manager
from app.db.session import async_session_factory
from app.deps import resolve_user
from app.schemas.ws_messages import EndSessionMessage, StartSessionMessage

router = APIRouter()


@router.websocket("/ws/calls/{call_id}")
async def call_session(websocket: WebSocket, call_id: uuid.UUID, token: str = Query(...)):
    await websocket.accept()

    async with async_session_factory() as db:
        try:
            user = await resolve_user(token, db)
        except HTTPException:
            await websocket.close(code=4401, reason="invalid token")
            return

    session = None

    try:
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                break

            if message.get("text") is not None:
                try:
                    payload = json.loads(message["text"])
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "detail": "invalid JSON"})
                    continue

                msg_type = payload.get("type")

                if msg_type == "start_session":
                    try:
                        body = StartSessionMessage.model_validate(payload)
                    except ValidationError as exc:
                        await websocket.send_json({"type": "error", "detail": str(exc)})
                        continue

                    session = session_manager.start_session(
                        call_id=call_id, user_id=user.id, phone_number=body.phone_number
                    )
                    await websocket.send_json(
                        {"type": "session_started", "call_id": str(call_id)}
                    )

                elif msg_type == "end_session":
                    EndSessionMessage.model_validate(payload)
                    await websocket.send_json(
                        {
                            "type": "session_summary",
                            "audio_chunks_received": (
                                session.audio_chunks_received if session else 0
                            ),
                        }
                    )
                    break

                else:
                    await websocket.send_json(
                        {"type": "error", "detail": f"unknown message type: {msg_type}"}
                    )

            elif message.get("bytes") is not None:
                if session is None:
                    await websocket.send_json(
                        {"type": "error", "detail": "audio_chunk before start_session"}
                    )
                    continue
                session.audio_chunks_received += 1

    except WebSocketDisconnect:
        pass
    finally:
        if session is not None:
            session_manager.end_session(call_id)
