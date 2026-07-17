import asyncio
import json
import logging
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
logger = logging.getLogger(__name__)

KEEPALIVE_INTERVAL_SECONDS = 20


class _Sender:
    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket
        self._lock = asyncio.Lock()

    async def send(self, payload: dict) -> None:
        async with self._lock:
            await self._websocket.send_json(payload)


async def _keepalive_loop(sender: _Sender) -> None:
    while True:
        await asyncio.sleep(KEEPALIVE_INTERVAL_SECONDS)
        await sender.send({"type": "ping"})


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
        logger.warning("gemini analysis failed for call_id=%s, skipping window", session.call_id)
        return None

    session.rolling_context = result.updated_context
    session.last_is_suspicious = result.is_suspicious
    session.last_confidence = result.confidence
    session.last_reason = result.reason
    session.last_flagged_keywords = result.flagged_keywords
    return result


async def _analyze_window_and_maybe_flag(sender: _Sender, session: CallSession, window: bytes) -> None:
    result = await _run_analysis(session, window)
    if result is None:
        return

    await sender.send(
        {
            "type": "analysis_result",
            "is_suspicious": result.is_suspicious,
            "confidence": result.confidence,
            "reason": result.reason,
            "flagged_keywords": result.flagged_keywords,
        }
    )

    if (
        session.state == CallState.MONITORING
        and result.is_suspicious
        and result.confidence >= settings.suspicion_confidence_threshold
    ):
        session.state = CallState.SUSPICIOUS_FLAGGED
        logger.info("call_id=%s flagged suspicious (confidence=%.2f)", session.call_id, result.confidence)


async def _finish_session(sender: _Sender, session: CallSession) -> None:
    async with async_session_factory() as db:
        log_id = await log_service.persist_call_log(db, session)

    logger.info(
        "call_id=%s ended: verification_status=%s user_action=%s",
        session.call_id,
        session.verification_status.value,
        session.last_user_action.value if session.last_user_action else None,
    )

    await sender.send(
        {
            "type": "session_summary",
            "log_id": str(log_id),
            "audio_chunks_received": session.audio_chunks_received,
            "windows_ready": session.windows_ready,
            "verification_status": session.verification_status.value,
        }
    )


async def _handle_audio_chunk(sender: _Sender, session: CallSession, data: bytes) -> None:
    session.audio_chunks_received += 1
    session.buffer.add_chunk(data)

    while session.buffer.has_full_window():
        window = session.buffer.pop_window()
        session.windows_ready += 1

        if session.state != CallState.MONITORING:
            continue

        await _analyze_window_and_maybe_flag(sender, session, window)


async def _handle_user_decision(sender: _Sender, session: CallSession, payload: dict) -> bool:
    try:
        body = UserDecisionMessage.model_validate(payload)
    except ValidationError as exc:
        await sender.send({"type": "error", "detail": str(exc)})
        return False

    if session.state == CallState.SUSPICIOUS_FLAGGED:
        if body.choice == "tutup":
            session.last_user_action = UserAction.TUTUP_PANGGILAN
            await _finish_session(sender, session)
            return True

        if body.choice == "lanjutkan":
            session.state = CallState.AWAITING_VOICE_CHECK
            await sender.send({"type": "request_voice_check"})
            return False

        await sender.send(
            {"type": "error", "detail": "expected 'tutup' or 'lanjutkan' in this state"}
        )
        return False

    if session.state == CallState.AWAITING_RISK_DECISION:
        if body.choice == "tutup":
            session.last_user_action = UserAction.TUTUP_PANGGILAN
            await _finish_session(sender, session)
            return True

        if body.choice == "lanjut_risiko_sendiri":
            session.last_user_action = UserAction.LANJUT_RISIKO_SENDIRI
            session.state = CallState.MONITORING
            await sender.send({"type": "resumed_monitoring"})
            return False

        await sender.send(
            {"type": "error", "detail": "expected 'tutup' or 'lanjut_risiko_sendiri' in this state"}
        )
        return False

    await sender.send({"type": "error", "detail": "no decision expected right now"})
    return False


async def _handle_voice_check_response(sender: _Sender, session: CallSession, payload: dict) -> None:
    if session.state != CallState.AWAITING_VOICE_CHECK:
        await sender.send({"type": "error", "detail": "voice check not expected now"})
        return

    try:
        body = VoiceCheckResponseMessage.model_validate(payload)
    except ValidationError as exc:
        await sender.send({"type": "error", "detail": str(exc)})
        return

    if not body.recognized:
        session.state = CallState.AWAITING_RISK_DECISION
        await sender.send({"type": "high_risk_warning"})
        return

    async with async_session_factory() as db:
        if not await families_service.is_member(db, body.family_id, session.user_id):
            await sender.send({"type": "error", "detail": "not a member of that family"})
            return

    session.claimed_family_id = body.family_id
    session.codeword_retries_left = session_manager.CODEWORD_MAX_RETRIES
    session.state = CallState.AWAITING_CODEWORD
    await sender.send({"type": "request_codeword"})


async def _handle_codeword_submit(sender: _Sender, session: CallSession, payload: dict) -> None:
    if session.state != CallState.AWAITING_CODEWORD:
        await sender.send({"type": "error", "detail": "codeword not expected now"})
        return

    try:
        body = CodewordSubmitMessage.model_validate(payload)
    except ValidationError as exc:
        await sender.send({"type": "error", "detail": str(exc)})
        return

    async with async_session_factory() as db:
        secret = await families_service.get_decrypted_secret(db, session.claimed_family_id)

    if secret is not None and verify_codeword(secret, body.value):
        session.verification_status = VerificationStatus.TERVERIFIKASI
        session.state = CallState.MONITORING
        logger.info("call_id=%s codeword verified", session.call_id)
        await sender.send({"type": "codeword_result", "status": "verified"})
        return

    session.codeword_retries_left -= 1

    if session.codeword_retries_left > 0:
        await sender.send(
            {
                "type": "codeword_result",
                "status": "failed",
                "retries_left": session.codeword_retries_left,
            }
        )
        return

    session.verification_status = VerificationStatus.GAGAL
    session.state = CallState.AWAITING_RISK_DECISION
    logger.warning("call_id=%s codeword verification exhausted retries", session.call_id)
    await sender.send({"type": "codeword_result", "status": "failed", "retries_left": 0})


@router.websocket("/ws/calls/{call_id}")
async def call_session(websocket: WebSocket, call_id: uuid.UUID, token: str = Query(...)):
    await websocket.accept()

    async with async_session_factory() as db:
        try:
            user = await resolve_user(token, db)
        except HTTPException:
            logger.warning("call_id=%s rejected: invalid token", call_id)
            await websocket.close(code=4401, reason="invalid token")
            return

    sender = _Sender(websocket)
    keepalive_task = asyncio.create_task(_keepalive_loop(sender))
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
                    await sender.send({"type": "error", "detail": "invalid JSON"})
                    continue

                msg_type = payload.get("type")

                if msg_type == "start_session":
                    try:
                        body = StartSessionMessage.model_validate(payload)
                    except ValidationError as exc:
                        await sender.send({"type": "error", "detail": str(exc)})
                        continue

                    session = session_manager.start_session(
                        call_id=call_id, user_id=user.id, phone_number=body.phone_number
                    )
                    logger.info("call_id=%s session started", call_id)
                    await sender.send({"type": "session_started", "call_id": str(call_id)})

                elif msg_type == "end_session":
                    EndSessionMessage.model_validate(payload)
                    if session is not None:
                        remainder = session.buffer.flush_remainder()
                        if remainder is not None:
                            session.windows_ready += 1
                            if session.state == CallState.MONITORING:
                                await _analyze_window_and_maybe_flag(sender, session, remainder)
                        await _finish_session(sender, session)
                    break

                elif msg_type == "user_decision":
                    if session is None:
                        await sender.send({"type": "error", "detail": "no active session"})
                        continue
                    finished = await _handle_user_decision(sender, session, payload)
                    if finished:
                        break

                elif msg_type == "voice_check_response":
                    if session is None:
                        await sender.send({"type": "error", "detail": "no active session"})
                        continue
                    await _handle_voice_check_response(sender, session, payload)

                elif msg_type == "codeword_submit":
                    if session is None:
                        await sender.send({"type": "error", "detail": "no active session"})
                        continue
                    await _handle_codeword_submit(sender, session, payload)

                else:
                    await sender.send(
                        {"type": "error", "detail": f"unknown message type: {msg_type}"}
                    )

            elif message.get("bytes") is not None:
                if session is None:
                    await sender.send(
                        {"type": "error", "detail": "audio_chunk before start_session"}
                    )
                    continue

                await _handle_audio_chunk(sender, session, message["bytes"])

    except WebSocketDisconnect:
        pass
    finally:
        keepalive_task.cancel()
        try:
            await keepalive_task
        except asyncio.CancelledError:
            pass
        if session is not None:
            session_manager.end_session(call_id)
