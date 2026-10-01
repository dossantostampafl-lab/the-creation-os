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
from app.inference.contracts import InferenceError
from app.repositories.domain import DomainRepository
from app.schemas.auth import TokenPayload
from app.voice_session.acknowledgement import VoiceAcknowledgementCache
from app.voice_session.conversation import VoiceConversationBridge
from app.voice_session.local import KokoroRealtimeTTS, VoskRealtimeSTT, get_local_engine
from app.voice_session.protocol import ClientEvent
from app.voice_session.runtime import build_primary_provider
from app.voice_session.session import VoiceSession, VoiceSessionGateway
from app.voice_session.tickets import consume_voice_ticket, issue_voice_ticket
from app.voice_session.tts import VoiceSynthesisError

router = APIRouter()
MAX_AUDIO_FRAME_BYTES = 64 * 1024
_acknowledgement_cache: VoiceAcknowledgementCache | None = None
_acknowledgement_profile: str | None = None


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


def _voice_configured() -> bool:
    return settings.deus_voice_session_enabled


async def _local_tts_factory():
    return KokoroRealtimeTTS(await get_local_engine())


def _voice_acknowledgement_cache() -> VoiceAcknowledgementCache:
    global _acknowledgement_cache, _acknowledgement_profile
    if not _voice_configured():
        raise RuntimeError("Realtime voice is not configured")
    profile = settings.deus_local_voice_models_dir
    if _acknowledgement_cache is None or _acknowledgement_profile != profile:
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def factory():
            async with await _local_tts_factory() as tts:
                yield tts
        _acknowledgement_cache = VoiceAcknowledgementCache(factory, timeout_seconds=120.0)
        _acknowledgement_profile = profile
    return _acknowledgement_cache


@router.get("/voice/session/acknowledgement")
async def get_voice_session_acknowledgement(
    _creator: TokenPayload = Depends(get_sovereign_creator),
) -> Response:
    if not _voice_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "VOICE_SESSION_NOT_CONFIGURED",
                    "message": "A voz local ainda não foi ativada.", "nonretryable": True},
        )
    try:
        audio = await _voice_acknowledgement_cache().get()
    except VoiceSynthesisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": exc.code, "message": str(exc), "nonretryable": exc.nonretryable},
        ) from exc
    except (ImportError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "VOICE_MODELS_UNAVAILABLE",
                    "message": "Os modelos locais de voz não estão disponíveis.", "nonretryable": True},
        ) from exc
    except (RuntimeError, TimeoutError) as exc:
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

    if not _voice_configured():
        await websocket.accept()
        await websocket.send_json(
            {
                "type": "error",
                "code": "VOICE_SESSION_NOT_CONFIGURED",
                "message": "Realtime DEUS voice is not configured.",
                "nonretryable": True,
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

    try:
        engine = await get_local_engine()
    except (RuntimeError, OSError, ImportError):
        await websocket.accept()
        await websocket.send_json({
            "type": "error", "code": "VOICE_MODELS_UNAVAILABLE",
            "message": "Os modelos locais de voz não estão disponíveis.",
            "nonretryable": True,
        })
        await websocket.close(code=1013)
        return
    stt_client = VoskRealtimeSTT(engine.recognizer(), silence_ms=settings.deus_local_voice_silence_ms)

    def tts_factory():
        return KokoroRealtimeTTS(engine)

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

        await websocket.accept()
        try:
            async with stt_client as stt:
                gateway = VoiceSessionGateway(
                    session=session,
                    stt=stt,
                    primary=primary,
                    tts_factory=tts_factory,
                    request_builder=bridge.build_request,
                    on_turn_completed=bridge.complete_turn,
                    first_token_timeout_seconds=(
                        settings.deus_voice_first_token_timeout_ms / 1000
                    ),
                )

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
                receiver = asyncio.create_task(websocket.receive_json())
                try:
                    while True:
                        done, _pending = await asyncio.wait(
                            (pump, receiver),
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if pump in done:
                            await pump
                            return
                        payload = receiver.result()
                        receiver = asyncio.create_task(websocket.receive_json())
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
                            if cancelled:
                                pump.cancel()
                                await asyncio.gather(pump, return_exceptions=True)
                                pump = asyncio.create_task(transcript_pump())
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
                    receiver.cancel()
                    await asyncio.gather(pump, receiver, return_exceptions=True)
        except VoiceSynthesisError as exc:
            try:
                await send_json({
                    "type": "error", "code": exc.code, "message": str(exc),
                    "nonretryable": exc.nonretryable,
                })
                await websocket.close(code=1008 if exc.nonretryable else 1013)
            except (RuntimeError, WebSocketDisconnect):
                pass
        except (RuntimeError, OSError, TimeoutError, InferenceError):
            try:
                await send_json(
                    {
                        "type": "error",
                        "code": "VOICE_STT_UNAVAILABLE",
                        "message": "Realtime speech recognition is unavailable.",
                    }
                )
                await websocket.close(code=1013)
            except (RuntimeError, WebSocketDisconnect):
                pass
