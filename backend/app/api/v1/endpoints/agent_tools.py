"""Tool schemas intended for OpenAI and Anthropic-compatible agents."""

from fastapi import APIRouter

from .routing import AgentTripRequest

router = APIRouter(prefix="/api/v1/agent-tools", tags=["agent-tools"])

# Generated from the endpoint's request model so the two cannot drift apart.
CALCULATE_MULTIMODAL_TRIP_TOOL = {
    "type": "function",
    "function": {
        "name": "calculate_multimodal_trip",
        "description": (
            "Calculates a multimodal route (road + high-speed rail) and its carbon "
            "footprint (ADEME emission factors) between two addresses. "
            "Call POST /api/v1/agent-tools/calculate-trip with these arguments."
        ),
        "parameters": AgentTripRequest.model_json_schema(),
    },
}


@router.get(
    "/schema",
    summary="Get the multimodal agent tool schema",
    description="Returns a provider-neutral OpenAI Function Calling tool definition.",
)
async def tool_schema() -> dict:
    return CALCULATE_MULTIMODAL_TRIP_TOOL
