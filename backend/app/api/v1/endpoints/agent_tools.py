"""Tool schemas intended for OpenAI and Anthropic-compatible agents."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/agent-tools", tags=["agent-tools"])

CALCULATE_MULTIMODAL_TRIP_TOOL = {
    "type": "function",
    "function": {
        "name": "calculate_multimodal_trip",
        "description": (
            "Calculates optimal multimodal route (road + high-speed rail) "
            "and certified ADEME carbon footprint between origin and destination coordinates."
        ),
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "origin_lat": {"type": "number", "minimum": -90, "maximum": 90},
                "origin_lon": {"type": "number", "minimum": -180, "maximum": 180},
                "dest_lat": {"type": "number", "minimum": -90, "maximum": 90},
                "dest_lon": {"type": "number", "minimum": -180, "maximum": 180},
                "preference": {
                    "type": "string",
                    "enum": ["fastest", "lowest_carbon"],
                },
            },
            "required": [
                "origin_lat",
                "origin_lon",
                "dest_lat",
                "dest_lon",
                "preference",
            ],
        },
    },
}


@router.get(
    "/schema",
    summary="Get the multimodal agent tool schema",
    description="Returns a provider-neutral OpenAI Function Calling tool definition.",
)
async def tool_schema() -> dict:
    return CALCULATE_MULTIMODAL_TRIP_TOOL
