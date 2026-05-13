"""ADK agent chat endpoint."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agents.fraud_agent import build_fraud_agent

router = APIRouter(prefix="/agent", tags=["ADK Fraud Agent"])

_AGENT = None


def _get_agent():
    global _AGENT
    if _AGENT is None:
        _AGENT = build_fraud_agent()
    return _AGENT


class AgentRequest(BaseModel):
    message: str = Field(..., min_length=5, description="Message to the fraud detection agent")
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])


class AgentResponse(BaseModel):
    response: str
    session_id: str
    backend: str


@router.post("/chat", response_model=AgentResponse, summary="Chat with fraud agent")
async def chat_with_agent(body: AgentRequest) -> AgentResponse:
    """
    Send a natural language message to the ADK fraud detection agent.
    The agent can call all fraud detection tools and query the knowledge base.

    Example messages:
    - "What are the risk indicators for transaction ABC123?"
    - "Analyze the recent velocity patterns for card 4521"
    - "What compliance rules apply to structuring?"
    - "Show me the fraud statistics for the last 24 hours"
    """
    agent = _get_agent()
    response_text = await agent.run(body.message, session_id=body.session_id)
    return AgentResponse(
        response=response_text,
        session_id=body.session_id,
        backend=agent.backend,
    )


@router.get("/status", summary="Agent status")
def agent_status() -> dict[str, Any]:
    """Check the ADK agent's current status and backend."""
    agent = _get_agent()
    return {
        "status": "ready",
        "backend": agent.backend,
        "tools_available": [
            "tool_analyze_transaction",
            "tool_score_risk",
            "tool_detect_pattern",
            "tool_card_velocity",
            "tool_search_transactions",
            "tool_fraud_statistics",
            "tool_query_knowledge_base",
        ],
    }
