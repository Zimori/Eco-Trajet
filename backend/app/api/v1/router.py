"""Central versioned API router."""

from fastapi import APIRouter

from .endpoints.agent_tools import router as agent_tools_router

router = APIRouter()
router.include_router(agent_tools_router)
