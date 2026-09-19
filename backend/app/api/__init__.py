from fastapi import APIRouter

from app.api.automation import router as automation_router
from app.api.cache_status import router as cache_status_router
from app.api.central_core import router as central_core_router
from app.api.creator_interface import router as creator_interface_router
from app.api.deus import router as deus_router
from app.api.dispatch import router as dispatch_router
from app.api.execution import router as execution_router
from app.api.health import router as health_router
from app.api.inference_status import router as inference_status_router
from app.api.kernel import router as kernel_router
from app.api.living_core import router as living_core_router
from app.api.malkuth import router as malkuth_router
from app.api.memory import router as memory_router
from app.api.mission_authorization import router as mission_authorization_router
from app.api.opportunities import router as opportunities_router
from app.api.perception import router as perception_router
from app.api.planner import router as planner_router
from app.api.rockmam import router as rockmam_router
from app.api.sophia import router as sophia_router
from app.api.system_state import router as system_state_router
from app.api.tree_core import router as tree_core_router
from app.api.trinity import router as trinity_router
from app.api.voice import router as voice_router
from app.api.workers import router as workers_router

router = APIRouter()

# Core/runtime health first.
router.include_router(health_router)

# Creator/living surface.
router.include_router(creator_interface_router)
router.include_router(living_core_router)
router.include_router(deus_router)

# Execution and orchestration. Static execution routes must precede dynamic
# /agents/{agent_id} routes from tree_core.
router.include_router(dispatch_router)
router.include_router(planner_router)
router.include_router(workers_router)
router.include_router(execution_router)
router.include_router(tree_core_router)
router.include_router(central_core_router)
router.include_router(kernel_router)
router.include_router(malkuth_router)

# Cognitive / memory / governance.
router.include_router(memory_router)
router.include_router(mission_authorization_router)
router.include_router(sophia_router)
router.include_router(rockmam_router)
router.include_router(trinity_router)

# Automation and perception.
router.include_router(automation_router)
router.include_router(opportunities_router)
router.include_router(perception_router)
router.include_router(voice_router)

# Current read models / inference / semantic cache surfaces.
router.include_router(system_state_router)
router.include_router(inference_status_router)
router.include_router(cache_status_router)
