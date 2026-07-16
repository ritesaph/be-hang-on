import json
import uuid

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.calls import log_service, session_manager
from app.calls.session_manager import CallSession, CallState
from app.codeword.totp import verify_codeword
from app.config import settings
from app.db.models import UserAction, VerificationStatus
from app.db.session import async_session_factory
from app.deps import resolve_user
from app.families import service as families_service
from app.gemini.client import GeminiAnalysisError, analyze_window
from app.gemini.schemas import SuspicionAnalysis
from app.schemas.ws_messages import (
    CodewordSubmitMessage,
    EndSessionMessage,
    StartSessionMessage,
    UserDecisionMessage,
    VoiceCheckResponseMessage,
)

router = APIRouter()


async def _run_analysis(session: CallSession, pcm_window: bytes) -> SuspicionAnalysis | None:
    try:
        result = await analyze_window(
            pcm_audio=pcm_window,
            rolling_context=session.rolling_context,
            sample_rate=session.buffer.sample_rate,
            channels=session.buffer.channels,
            bytes_per_sample=session.buffer.bytes_per_sample,
        )
    except GeminiAnalysisError:
        return None

    session.rolling_context = result.updated_context
    session.last_is_suspicious = result.is_suspicious
    session.last_confidence = result.confidence
    session.last_reason = result.reason
    return result


async def _analyze_window_and_maybe_flag(websocket: WebSocket, session: CallSession, window: bytes) -> None:
    result = await _run_analysis(session, window)
    if result is None:
        return

    await websocket.send_json(
        {
            "type": "analysis_result",
            "is_suspicious": result.is_suspicious,
            "confidence": result.confidence,
            "reason": result.reason,
        }
    )

    if (
        session.state == CallState.MONITORING
        and result.is_suspicious
        and result.confidence >= settings.suspicion_confidence_threshold
    ):
        session.state = CallState.SUSPICIOUS_FLAGGED


async def _finish_session(websocket: WebSocket, session: CallSession) -> None:
    async with async_session_factory() as db:
        log_id = await log_service.persist_call_log(db, session)

    await websocket.send_json(
        {
            "type": "session_summary",
            "log_id": str(log_id),
            "audio_chunks_received": session.audio_chunks_received,
            "windows_ready": session.windows_ready,
            "verification_status": session.verification_status.value,
        }
    )


async def _handle_audio_chunk(websocket: WebSocket, session: CallSession, data: bytes) -> None:
    session.audio_chunks_received += 1
    session.buffer.add_chunk(data)

    while session.buffer.has_full_window():
        window = session.buffer.pop_window()
        session.windows_ready += 1

        if session.state != CallState.MONITORING:
            continue

        await _analyze_window_and_maybe_flag(websocket, session, window)


async def _handle_user_decision(websocket: WebSocket, session: CallSession, payload: dict) -> bool:
    try:
        body = UserDecisionMessage.model_validate(payload)
    except ValidationError as exc:
        await websocket.send_json({"type": "error", "detail": str(exc)})
        return False

    if session.state == CallState.SUSPICIOUS_FLAGGED:
        if body.choice == "tutup":
            session.last_user_action = UserAction.TUTUP_PANGGILAN
            await _finish_session(websocket, session)
            return True

        if body.choice == "lanjutkan":
            session.state = CallState.AWAITING_VOICE_CHECK
            await websocket.send_json({"type": "request_voice_check"})
            return False

        await websocket.send_json(
            {"type": "error", "detail": "expected 'tutup' or 'lanjutkan' in this state"}
        )
        return False

    if session.state == CallState.AWAITING_RISK_DECISION:
        if body.choice == "tutup":
            session.last_user_action = UserAction.TUTUP_PANGGILAN
            await _finish_session(websocket, session)
            return True

        if body.choice == "lanjut_risiko_sendiri":
            session.last_user_action = UserAction.LANJUT_RISIKO_SENDIRI
            session.state = CallState.MONITORING
            await websocket.send_json({"type": "resumed_monitoring"})
            return False

        await websocket.send_json(
            {"type": "error", "detail": "expected 'tutup' or 'lanjut_risiko_sendiri' in this state"}
        )
        return False

    await websocket.send_json({"type": "error", "detail": "no decision expected right now"})
    return False


async def _handle_voice_check_response(
    websocket: WebSocket, session: CallSession, payload: dict
) -> None:
    if session.state != CallState.AWAITING_VOICE_CHECK:
        await websocket.send_json({"type": "error", "detail": "voice check not expected now"})
        return

    try:
        body = VoiceCheckResponseMessage.model_validate(payload)
    except ValidationError as exc:
        await websocket.send_json({"type": "error", "detail": str(exc)})
        return

    if not body.recognized:
        session.state = CallState.AWAITING_RISK_DECISION
        await websocket.send_json({"type": "high_risk_warning"})
        return

    async with async_session_factory() as db:
        if not await families_service.is_member(db, body.family_id, session.user_id):
            await websocket.send_json({"type": "error", "detail": "not a member of that family"})
            return

    session.claimed_family_id = body.family_id
    session.codeword_retries_left = session_manager.CODEWORD_MAX_RETRIES
    session.state = CallState.AWAITING_CODEWORD
    await websocket.send_json({"type": "request_codeword"})


async def _handle_codeword_submit(websocket: WebSocket, session: CallSession, payload: dict) -> None:
    if session.state != CallState.AWAITING_CODEWORD:
        await websocket.send_json({"type": "error", "detail": "codeword not expected now"})
        return

    try:
        body = CodewordSubmitMessage.model_validate(payload)
    except ValidationError as exc:
        await websocket.send_json({"type": "error", "detail": str(exc)})
        return

    async with async_session_factory() as db:
        secret = await families_service.get_decrypted_secret(db, session.claimed_family_id)

    if secret is not None and verify_codeword(secret, body.value):
        session.verification_status = VerificationStatus.TERVERIFIKASI
        session.state = CallState.MONITORING
        await websocket.send_json({"type": "codeword_result", "status": "verified"})
        return

    session.codeword_retries_left -= 1

    if session.codeword_retries_left > 0:
        await websocket.send_json(
            {
                "type": "codeword_result",
                "status": "failed",
                "retries_left": session.codeword_retries_left,
            }
        )
        return

    session.verification_status = VerificationStatus.GAGAL
    session.state = CallState.AWAITING_RISK_DECISION
    await websocket.send_json(
        {"type": "codeword_result", "status": "failed", "retries_left": 0}
    )


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
                    if session is not None:
                        remainder = session.buffer.flush_remainder()
                        if remainder is not None:
                            session.windows_ready += 1
                            if session.state == CallState.MONITORING:
                                await _analyze_window_and_maybe_flag(websocket, session, remainder)
                        await _finish_session(websocket, session)
                    break

                elif msg_type == "user_decision":
                    if session is None:
                        await websocket.send_json(
                            {"type": "error", "detail": "no active session"}
                        )
                        continue
                    finished = await _handle_user_decision(websocket, session, payload)
                    if finished:
                        break

                elif msg_type == "voice_check_response":
                    if session is None:
                        await websocket.send_json(
                            {"type": "error", "detail": "no active session"}
                        )
                        continue
                    await _handle_voice_check_response(websocket, session, payload)

                elif msg_type == "codeword_submit":
                    if session is None:
                        await websocket.send_json(
                            {"type": "error", "detail": "no active session"}
                        )
                        continue
                    await _handle_codeword_submit(websocket, session, payload)

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

                await _handle_audio_chunk(websocket, session, message["bytes"])

    except WebSocketDisconnect:
        pass
    finally:
        if session is not None:
            session_manager.end_session(call_id)
