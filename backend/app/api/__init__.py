from fastapi import APIRouter

from app.api.builds import router as builds_router
from app.api.cache_status import router as cache_status_router
from app.api.cyber_range import router as cyber_range_router
from app.api.deus import router as deus_router
from app.api.health import router as health_router
from app.api.inference_status import router as inference_status_router
from app.api.kernel import router as kernel_router
from app.api.knowledge import router as knowledge_router
from app.api.living_core import router as living_core_router
from app.api.opportunity_state import router as opportunity_state_router
from app.api.range_training import router as range_training_router
from app.api.security_task_force import router as security_task_force_router
from app.api.system_state import router as system_state_router
from app.api.voice_session import router as voice_session_router

router = APIRouter()
router.include_router(health_router)
router.include_router(cyber_range_router)
router.include_router(knowledge_router)
router.include_router(living_core_router)
router.include_router(opportunity_state_router)
router.include_router(deus_router)
router.include_router(kernel_router)
router.include_router(system_state_router)
router.include_router(inference_status_router)
router.include_router(cache_status_router)
router.include_router(voice_session_router)
router.include_router(security_task_force_router)

router.include_router(builds_router)
router.include_router(range_training_router)
