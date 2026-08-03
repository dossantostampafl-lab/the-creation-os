from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_sovereign_creator
from app.core.domain import Actor, InceptionStatus, MissionStatus
from app.db.session import get_session
from app.repositories.domain import DomainRepository
from app.repositories.god import GodConversationRepository
from app.schemas.auth import TokenPayload
from app.schemas.conversation import ConversationCreateRequest, ConversationMessageResponse, ConversationResponse, MessageRequest
from app.schemas.god import GodConversationRequest, GodConversationResponse
from app.schemas.inception import InceptionCreateRequest, InceptionDecisionRequest, InceptionResponse
from app.schemas.mission import MissionCreateRequest, MissionPlanRequest, MissionResponse
from app.services.domain import LivingCoreService
from app.services.god import GodConversationService

router = APIRouter()


def correlation_id(x_correlation_id: str | None = Header(None)) -> str:
    if x_correlation_id is None:
        return str(uuid.uuid4())
    return str(uuid.UUID(x_correlation_id))


def actor(token: TokenPayload = Depends(get_sovereign_creator)) -> Actor:
    return Actor(id=token.sub, role="creator")


def service(session: AsyncSession = Depends(get_session)) -> LivingCoreService:
    return LivingCoreService(DomainRepository(session))


def god_service(session: AsyncSession = Depends(get_session)) -> GodConversationService:
    return GodConversationService(GodConversationRepository(session))


def conversation_response(item) -> ConversationResponse:
    return ConversationResponse(**{name: getattr(item, name) for name in ConversationResponse.model_fields})


def inception_response(item) -> InceptionResponse:
    return InceptionResponse(id=item.id, conversation_id=item.conversation_id, title=item.title,
        description=item.description, status=item.status, trinity_assessment=item.trinity_assessment_json,
        proposed_at=item.proposed_at, decided_at=item.decided_at, decided_by=item.decided_by,
        decision_reason=item.decision_reason)


def mission_response(item) -> MissionResponse:
    return MissionResponse(**{name: getattr(item, name) for name in MissionResponse.model_fields})


def god_conversation_response(item) -> GodConversationResponse:
    return GodConversationResponse(
        id=item.id,
        conversation_id=item.conversation_id,
        message_id=item.creator_message_id,
        god_message_id=item.god_message_id,
        interaction_type=item.interaction_type,
        reply=item.response_payload["reply"],
        potential_detected=item.potential_detected,
        next_action=item.response_payload["next_action"],
        memory_context=item.response_payload.get("memory_context", []),
        fingerprint=item.fingerprint,
        created_at=item.created_at,
        completed_at=item.completed_at,
    )


@router.post("/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(body: ConversationCreateRequest, a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: LivingCoreService = Depends(service)):
    return conversation_response(await s.create_conversation(a, body.title, cid))


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(a: Actor = Depends(actor), s: LivingCoreService = Depends(service)):
    return [conversation_response(x) for x in await s.conversations(a)]


@router.get("/conversations/{entity_id}", response_model=ConversationResponse)
async def get_conversation(entity_id: uuid.UUID, a: Actor = Depends(actor), s: LivingCoreService = Depends(service)):
    return conversation_response(await s.conversation(a, str(entity_id)))


@router.post("/conversations/{entity_id}/messages", response_model=ConversationMessageResponse, status_code=201)
async def add_message(entity_id: uuid.UUID, body: MessageRequest, a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: LivingCoreService = Depends(service)):
    item = await s.add_message(a, str(entity_id), body.content, body.metadata, cid)
    return ConversationMessageResponse(**{name: getattr(item, name) for name in ConversationMessageResponse.model_fields})


@router.get("/conversations/{entity_id}/messages", response_model=list[ConversationMessageResponse])
async def list_conversation_messages(entity_id: uuid.UUID, a: Actor = Depends(actor), s: LivingCoreService = Depends(service)):
    return [
        ConversationMessageResponse(**{name: getattr(item, name) for name in ConversationMessageResponse.model_fields})
        for item in await s.messages(a, str(entity_id))
    ]


@router.post(
    "/living-core/conversations/{entity_id}/god",
    response_model=GodConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def orchestrate_god_conversation(
    entity_id: uuid.UUID,
    body: GodConversationRequest,
    response: Response,
    a: Actor = Depends(actor),
    cid: str = Depends(correlation_id),
    s: GodConversationService = Depends(god_service),
):
    item, created = await s.interact(a, str(entity_id), body.message, body.idempotency_key, cid)
    if not created:
        response.status_code = status.HTTP_200_OK
    return god_conversation_response(item)


@router.post("/conversations/{entity_id}/close", response_model=ConversationResponse)
async def close_conversation(entity_id: uuid.UUID, a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: LivingCoreService = Depends(service)):
    return conversation_response(await s.close_conversation(a, str(entity_id), cid))


@router.post("/conversations/{entity_id}/archive", response_model=ConversationResponse)
async def archive_conversation(entity_id: uuid.UUID, a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: LivingCoreService = Depends(service)):
    return conversation_response(await s.archive_conversation(a, str(entity_id), cid))


@router.post("/inceptions", response_model=InceptionResponse, status_code=201)
async def create_inception(body: InceptionCreateRequest, a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: LivingCoreService = Depends(service)):
    return inception_response(await s.create_inception(a, body.conversation_id, body.source_message_id, body.title, body.description, cid))


@router.get("/inceptions", response_model=list[InceptionResponse])
async def list_inceptions(a: Actor = Depends(actor), s: LivingCoreService = Depends(service)):
    return [inception_response(x) for x in await s.inceptions(a)]


@router.get("/inceptions/{entity_id}", response_model=InceptionResponse)
async def get_inception(entity_id: uuid.UUID, a: Actor = Depends(actor), s: LivingCoreService = Depends(service)):
    return inception_response(await s.inception(a, str(entity_id)))


async def inception_action(entity_id, target, body, a, cid, s):
    return inception_response(await s.transition_inception(a, str(entity_id), target, cid, body.reason if body else None))


@router.post("/inceptions/{entity_id}/submit", response_model=InceptionResponse)
async def submit_inception(entity_id: uuid.UUID, a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: LivingCoreService = Depends(service)):
    return await inception_action(entity_id, InceptionStatus.AWAITING_CREATOR_DECISION, None, a, cid, s)


@router.post("/inceptions/{entity_id}/approve", response_model=InceptionResponse)
async def approve_inception(entity_id: uuid.UUID, body: InceptionDecisionRequest, a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: LivingCoreService = Depends(service)):
    return await inception_action(entity_id, InceptionStatus.APPROVED, body, a, cid, s)


@router.post("/inceptions/{entity_id}/reject", response_model=InceptionResponse)
async def reject_inception(entity_id: uuid.UUID, body: InceptionDecisionRequest, a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: LivingCoreService = Depends(service)):
    return await inception_action(entity_id, InceptionStatus.REJECTED, body, a, cid, s)


@router.post("/inceptions/{entity_id}/cancel", response_model=InceptionResponse)
async def cancel_inception(entity_id: uuid.UUID, body: InceptionDecisionRequest, a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: LivingCoreService = Depends(service)):
    return await inception_action(entity_id, InceptionStatus.CANCELLED, body, a, cid, s)


@router.post("/missions", response_model=MissionResponse, status_code=201)
async def create_mission(body: MissionCreateRequest, a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: LivingCoreService = Depends(service)):
    return mission_response(await s.create_mission(a, body.inception_id, body.title, body.objective, cid))


@router.get("/missions", response_model=list[MissionResponse])
async def list_missions(a: Actor = Depends(actor), s: LivingCoreService = Depends(service)):
    return [mission_response(x) for x in await s.missions(a)]


@router.get("/missions/{entity_id}", response_model=MissionResponse)
async def get_mission(entity_id: uuid.UUID, a: Actor = Depends(actor), s: LivingCoreService = Depends(service)):
    return mission_response(await s.mission(a, str(entity_id)))


async def mission_action(entity_id, target, plan, a, cid, s):
    return mission_response(await s.transition_mission(a, str(entity_id), target, cid, plan))


@router.post("/missions/{entity_id}/plan", response_model=MissionResponse)
async def plan_mission(entity_id: uuid.UUID, body: MissionPlanRequest, a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: LivingCoreService = Depends(service)):
    return await mission_action(entity_id, MissionStatus.PLANNED, body.model_dump(), a, cid, s)


@router.post("/missions/{entity_id}/validate", response_model=MissionResponse)
async def validate_mission(entity_id: uuid.UUID, a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: LivingCoreService = Depends(service)):
    return await mission_action(entity_id, MissionStatus.VALIDATED, None, a, cid, s)


@router.post("/missions/{entity_id}/authorize", response_model=MissionResponse)
async def authorize_mission(entity_id: uuid.UUID, a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: LivingCoreService = Depends(service)):
    return await mission_action(entity_id, MissionStatus.AUTHORIZED, None, a, cid, s)


@router.post("/missions/{entity_id}/cancel", response_model=MissionResponse)
async def cancel_mission(entity_id: uuid.UUID, a: Actor = Depends(actor), cid: str = Depends(correlation_id), s: LivingCoreService = Depends(service)):
    return await mission_action(entity_id, MissionStatus.CANCELLED, None, a, cid, s)
