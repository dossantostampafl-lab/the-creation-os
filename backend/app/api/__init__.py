from fastapi import APIRouter

from app.api.dispatch import router as dispatch_router
from app.api.execution import router as execution_router
from app.api.health import router as health_router
from app.api.living_core import router as living_core_router
from app.api.planner import router as planner_router
from app.api.tree_core import router as tree_core_router
from app.api.workers import router as workers_router

router = APIRouter()
router.include_router(health_router)
router.include_router(living_core_router)
router.include_router(tree_core_router)
router.include_router(dispatch_router)
router.include_router(planner_router)
router.include_router(workers_router)
router.include_router(execution_router)
