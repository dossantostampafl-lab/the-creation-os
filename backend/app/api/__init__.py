from fastapi import APIRouter

from app.api.deus import router as deus_router
from app.api.health import router as health_router
from app.api.inference_status import router as inference_status_router
from app.api.kernel import router as kernel_router
from app.api.living_core import router as living_core_router
from app.api.system_state import router as system_state_router

router = APIRouter()
router.include_router(health_router)
router.include_router(living_core_router)
router.include_router(deus_router)
router.include_router(kernel_router)
router.include_router(system_state_router)
router.include_router(inference_status_router)
