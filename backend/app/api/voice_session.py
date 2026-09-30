from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, WebSocket
from pydantic import BaseModel
from starlette.websockets import WebSocketDisconnect

from app.auth.dependencies import get_sovereign_creator
from app.schemas.auth import TokenPayload
from app.voice_session.protocol import ClientEvent
from app.voice_session.session import VoiceSession
from app.voice_session.tickets import consume_voice_ticket, issue_voice_ticket

router = APIRouter()


class VoiceTicketResponse(BaseModel):
    ticket: str


@router.post("/voice/session/ticket", response_model=VoiceTicketResponse, status_code=201)
async def create_voice_session_ticket(
    creator: TokenPayload = Depends(get_sovereign_creator),
) -> VoiceTicketResponse:
    return VoiceTicketResponse(ticket=await issue_voice_ticket(creator.sub))


@router.websocket("/voice/session")
async def voice_session_socket(
    websocket: WebSocket,
    ticket: str = Query(..., min_length=1),
) -> None:
    creator_id = await consume_voice_ticket(ticket)
    if creator_id is None:
        await websocket.close(code=4401)
        return

    session = VoiceSession(session_id=str(uuid.uuid4()))
    await websocket.accept()
    await websocket.send_json(
        {
            "type": "session_ready",
            "session_id": session.session_id,
            "creator_id": creator_id,
            "state": session.state.value,
            "turn_id": session.turn_id,
        }
    )

    try:
        while True:
            payload = await websocket.receive_json()
            event = ClientEvent.model_validate(payload)
            if event.session_id != session.session_id:
                await websocket.send_json(
                    {
                        "type": "stale_session",
                        "session_id": session.session_id,
                        "turn_id": session.turn_id,
                    }
                )
                continue
            if event.type == "barge_in":
                cancelled = session.barge_in(event.turn_id)
                await websocket.send_json(
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
