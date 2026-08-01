from fastapi import APIRouter

from app.api.automation import router as automation_router
from app.api.central_core import router as central_core_router
from app.api.creator_interface import router as creator_interface_router
from app.api.dispatch import router as dispatch_router
from app.api.execution import router as execution_router
from app.api.health import router as health_router
from app.api.living_core import router as living_core_router
from app.api.malkuth import router as malkuth_router
from app.api.memory import router as memory_router
from app.api.mission_authorization import router as mission_authorization_router
from app.api.opportunities import router as opportunities_router
from app.api.perception import router as perception_router
from app.api.planner import router as planner_router
from app.api.rockmam import router as rockmam_router
from app.api.sophia import router as sophia_router
from app.api.tree_core import router as tree_core_router
from app.api.trinity import router as trinity_router
from app.api.voice import router as voice_router
from app.api.workers import router as workers_router

router = APIRouter()
router.include_router(automation_router)
router.include_router(health_router)
router.include_router(creator_interface_router)
router.include_router(living_core_router)
router.include_router(dispatch_router)
router.include_router(planner_router)
router.include_router(workers_router)
# execution_router (prefix "/agents/executions") must be registered before
# tree_core_router (owns "GET /agents/{agent_id}") — otherwise FastAPI's
# route-matching order lets the single dynamic segment of tree_core's
# GET /agents/{agent_id} swallow GET /agents/executions first, making the
# execution-listing endpoint permanently unreachable (404/422 depending on
# the id shape). See docs/AUDIT_v0.5.md section 10 for how this was found.
router.include_router(execution_router)
router.include_router(tree_core_router)
router.include_router(central_core_router)
router.include_router(malkuth_router)
router.include_router(memory_router)
router.include_router(mission_authorization_router)
router.include_router(opportunities_router)
router.include_router(perception_router)
router.include_router(sophia_router)
router.include_router(rockmam_router)
router.include_router(trinity_router)
router.include_router(voice_router)
