from __future__ import annotations

import asyncio
import base64
import binascii
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, WebSocket, status
from pydantic import BaseModel, ValidationError
from starlette.websockets import WebSocketDisconnect

from app.auth.dependencies import get_sovereign_creator
from app.config import settings
from app.db.session import AsyncSessionLocal
from app.repositories.domain import DomainRepository
from app.schemas.auth import TokenPayload
from app.voice_session.acknowledgement import VoiceAcknowledgementCache
from app.voice_session.conversation import VoiceConversationBridge
from app.voice_session.protocol import ClientEvent
from app.voice_session.runtime import build_klaus_provider, build_primary_provider
from app.voice_session.session import VoiceSession, VoiceSessionGateway
from app.voice_session.stt import ElevenLabsRealtimeSTT, ElevenLabsSTTConfig
from app.voice_session.tickets import consume_voice_ticket, issue_voice_ticket
from app.voice_session.tts import ElevenLabsRealtimeTTS, ElevenLabsTTSConfig

router = APIRouter()
MAX_AUDIO_FRAME_BYTES = 64 * 1024
_acknowledgement_cache: VoiceAcknowledgementCache | None = None
_acknowledgement_profile: tuple[str, str] | None = None


class VoiceTicketResponse(BaseModel):
    ticket: str


def decode_audio_payload(event: ClientEvent) -> bytes:
    encoded = event.audio_base64
    if not encoded:
        raise ValueError("audio_base64 is required")
    try:
        audio = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("audio_base64 must be valid base64") from exc
    if not audio:
        raise ValueError("audio frame is empty")
    if len(audio) > MAX_AUDIO_FRAME_BYTES:
        raise ValueError("audio frame is too large")
    return audio


@router.post("/voice/session/ticket", response_model=VoiceTicketResponse, status_code=201)
async def create_voice_session_ticket(
    creator: TokenPayload = Depends(get_sovereign_creator),
) -> VoiceTicketResponse:
    return VoiceTicketResponse(ticket=await issue_voice_ticket(creator.sub))


def _voice_acknowledgement_cache() -> VoiceAcknowledgementCache:
    global _acknowledgement_cache, _acknowledgement_profile
    if (
        not settings.deus_voice_session_enabled
        or not settings.elevenlabs_enabled
        or settings.elevenlabs_api_key is None
    ):
        raise RuntimeError("Realtime ElevenLabs voice is not configured")

    profile = (settings.elevenlabs_voice_id, settings.elevenlabs_model_id)
    if _acknowledgement_cache is None or _acknowledgement_profile != profile:
        key = settings.elevenlabs_api_key.get_secret_value()
        config = ElevenLabsTTSConfig(
            api_key=key,
            voice_id=settings.elevenlabs_voice_id,
            model_id=settings.elevenlabs_model_id,
        )
        _acknowledgement_cache = VoiceAcknowledgementCache(
            lambda: ElevenLabsRealtimeTTS(config),
            timeout_seconds=max(5.0, settings.elevenlabs_timeout_seconds * 2),
        )
        _acknowledgement_profile = profile
    return _acknowledgement_cache


@router.get("/voice/session/acknowledgement")
async def get_voice_session_acknowledgement(
    _creator: TokenPayload = Depends(get_sovereign_creator),
) -> Response:
    try:
        audio = await _voice_acknowledgement_cache().get()
    except (RuntimeError, TimeoutError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Realtime DEUS acknowledgement is unavailable",
        ) from exc

    return Response(
        content=audio,
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-DEUS-Audio-Format": "pcm_s16le",
            "X-DEUS-Audio-Sample-Rate": "24000",
        },
    )


@router.websocket("/voice/session")
async def voice_session_socket(
    websocket: WebSocket,
    ticket: str = Query(..., min_length=1),
    conversation_id: str = Query(..., min_length=1),
) -> None:
    creator_id = await consume_voice_ticket(ticket)
    if creator_id is None:
        await websocket.close(code=4401)
        return

    if (
        not settings.deus_voice_session_enabled
        or not settings.elevenlabs_enabled
        or settings.elevenlabs_api_key is None
    ):
        await websocket.accept()
        await websocket.send_json(
            {
                "type": "error",
                "code": "VOICE_SESSION_NOT_CONFIGURED",
                "message": "Realtime DEUS voice is not configured.",
            }
        )
        await websocket.close(code=1013)
        return

    session = VoiceSession(session_id=str(uuid.uuid4()))
    send_lock = asyncio.Lock()

    async def send_json(payload: dict[str, object]) -> None:
        async with send_lock:
            await websocket.send_json(payload)

    try:
        primary = build_primary_provider()
        fallback = build_klaus_provider()
    except (RuntimeError, ValueError):
        await websocket.accept()
        await websocket.send_json(
            {
                "type": "error",
                "code": "VOICE_INFERENCE_NOT_CONFIGURED",
                "message": "Realtime DEUS inference is not configured.",
            }
        )
        await websocket.close(code=1013)
        return

    key = settings.elevenlabs_api_key.get_secret_value()
    stt_config = ElevenLabsSTTConfig(
        api_key=key,
        model_id=settings.elevenlabs_stt_model_id,
    )
    tts_config = ElevenLabsTTSConfig(
        api_key=key,
        voice_id=settings.elevenlabs_voice_id,
        model_id=settings.elevenlabs_model_id,
    )

    async with AsyncSessionLocal() as db:
        bridge = VoiceConversationBridge(
            DomainRepository(db),
            creator_id=creator_id,
            conversation_id=conversation_id,
        )
        try:
            await bridge.validate()
        except LookupError:
            await websocket.accept()
            await websocket.send_json(
                {
                    "type": "error",
                    "code": "CONVERSATION_NOT_FOUND",
                    "message": "Conversation not found.",
                }
            )
            await websocket.close(code=4404)
            return

        async with ElevenLabsRealtimeSTT(stt_config) as stt:
            gateway = VoiceSessionGateway(
                session=session,
                stt=stt,
                primary=primary,
                fallback=fallback,
                tts_factory=lambda: ElevenLabsRealtimeTTS(tts_config),
                request_builder=bridge.build_request,
                on_turn_completed=bridge.complete_turn,
                first_token_timeout_seconds=(
                    settings.deus_voice_first_token_timeout_ms / 1000
                ),
            )

            await websocket.accept()
            await send_json(
                {
                    "type": "session_ready",
                    "session_id": session.session_id,
                    "creator_id": creator_id,
                    "state": session.state.value,
                    "turn_id": session.turn_id,
                }
            )

            async def transcript_pump() -> None:
                while session.state.value != "CLOSED":
                    transcript = await stt.receive_transcript()
                    async for outbound in gateway.process_transcript(transcript):
                        await send_json(outbound)

            pump = asyncio.create_task(transcript_pump())
            try:
                while True:
                    payload = await websocket.receive_json()
                    try:
                        event = ClientEvent.model_validate(payload)
                    except ValidationError:
                        await send_json(
                            {
                                "type": "error",
                                "code": "INVALID_VOICE_EVENT",
                                "message": "Invalid voice event.",
                            }
                        )
                        continue

                    if event.session_id != session.session_id:
                        await send_json(
                            {
                                "type": "stale_session",
                                "session_id": session.session_id,
                                "turn_id": session.turn_id,
                            }
                        )
                        continue

                    if event.type == "audio":
                        try:
                            audio = decode_audio_payload(event)
                        except ValueError as exc:
                            await send_json(
                                {
                                    "type": "error",
                                    "code": "INVALID_AUDIO_FRAME",
                                    "message": str(exc),
                                }
                            )
                            continue
                        await gateway.send_audio(audio, commit=event.commit)
                        continue

                    if event.type == "commit":
                        await gateway.send_audio(b"", commit=True)
                        continue

                    if event.type == "barge_in":
                        cancelled = session.barge_in(event.turn_id)
                        await send_json(
                            {
                                "type": "barge_in",
                                "session_id": session.session_id,
                                "turn_id": event.turn_id,
                                "cancelled": cancelled,
                                "state": session.state.value,
                            }
                        )
                        continue

                    if event.type == "stop":
                        session.close()
                        await websocket.close(code=1000)
                        return
            except WebSocketDisconnect:
                session.close()
            finally:
                pump.cancel()
                await asyncio.gather(pump, return_exceptions=True)
