import pytest
import json
from unittest.mock import MagicMock
from app.services.copilot_agent import CopilotAgent
from app.services.review_agent import ReviewAgent
from app.services.app_context import AppContext
from app.models.user import User
from sqlalchemy.orm import Session

@pytest.mark.asyncio
async def test_copilot_agent_routing(db: Session, test_user: User, mocker):
    # Setup mock models
    mock_pro = mocker.MagicMock()
    mock_flash = mocker.MagicMock()
    
    # Setup mock tool call response
    mock_tool_call_msg = mocker.MagicMock()
    mock_tool_call_msg.tool_calls = [
        {"name": "get_watchlist", "args": {"user_id": test_user.id}, "id": "call_1"}
    ]
    
    # Setup final output response
    mock_final_msg = mocker.MagicMock()
    mock_final_msg.content = '{"answer": "Here is your watchlist", "evidence": [], "next_steps": []}'
    mock_final_msg.tool_calls = []

    # flash_with_tools yields tool calls first, then final answer on iteration 2
    mock_flash_with_tools = mocker.MagicMock()
    mock_flash_with_tools.invoke.side_effect = [mock_tool_call_msg, mock_final_msg]
    mock_flash.bind_tools.return_value = mock_flash_with_tools

    # Pro model fallback synthesis
    mock_pro.invoke.return_value = mock_final_msg

    # Mock tool map lookup in database
    mocker.patch("app.services.copilot_agent._TOOL_MAP", {
        "get_watchlist": mocker.MagicMock(invoke=lambda kwargs: {"success": True, "data": {"watchlist": [], "watchlist_symbols": [], "watchlist_count": 0}})
    })

    agent = CopilotAgent(pro_model=mock_pro, flash_model=mock_flash)
    
    # Run the agent
    response = agent.ask_copilot(db, test_user.id, "Show my watchlist")
    
    assert response["answer"] == "Here is your watchlist"
    assert mock_flash_with_tools.invoke.call_count == 2

@pytest.mark.asyncio
async def test_copilot_agent_streaming_parser(db: Session, test_user: User, mocker):
    mock_pro = mocker.MagicMock()
    mock_flash = mocker.MagicMock()
    
    # Mock stream generator yielding chunks of JSON response
    mock_chunks = [
        mocker.MagicMock(content='{'),
        mocker.MagicMock(content='"answer": "Hello World",'),
        mocker.MagicMock(content='"evidence": [], "next_steps": []}')
    ]
    
    async def mock_astream(*args, **kwargs):
        for chunk in mock_chunks:
            yield chunk

    # Bind mock to astream
    mock_pro.astream = mock_astream

    # Flash returns a direct answer (no tools) immediately to avoid loop
    mock_direct_msg = mocker.MagicMock()
    mock_direct_msg.tool_calls = []
    mock_direct_msg.content = '{"answer": "Hello World", "evidence": [], "next_steps": []}'

    mock_flash_with_tools = mocker.MagicMock()
    async def mock_ainvoke(*args, **kwargs):
        return mock_direct_msg
    mock_flash_with_tools.ainvoke = mock_ainvoke
    mock_flash.bind_tools.return_value = mock_flash_with_tools

    agent = CopilotAgent(pro_model=mock_pro, flash_model=mock_flash)
    
    # Retrieve stream
    stream_generator = agent.ask_copilot_stream(db, test_user.id, "Hello", temporary=True)
    events = []
    async for event in stream_generator:
        events.append(event)
        
    # Verify events
    assert any("Hello World" in e for e in events)

def test_review_agent_compilation(db: Session, test_user: User, mocker):
    mock_app_context = mocker.MagicMock()
    mock_app_context.pro_model = mocker.MagicMock()
    
    # Mock analyst response
    mock_analyst_msg = mocker.MagicMock()
    mock_analyst_msg.tool_calls = []
    mock_analyst_msg.content = json.dumps({
        "as_of": "2026-06-22",
        "portfolio_summary": {
            "current_value": "₹0.00",
            "total_pnl": "₹0.00",
            "total_pnl_percent": "0%",
            "analysis": "No active holdings."
        },
        "holdings_analysis": [],
        "rebalancing_plan": {
            "objective": "Balanced allocation",
            "steps": []
        },
        "future_scenarios": [],
        "news_updates": [],
        "caveat": "Standard SEBI caveat"
    })
    
    mock_model_bound = mocker.MagicMock()
    mock_model_bound.invoke.return_value = mock_analyst_msg
    mock_app_context.pro_model.bind_tools.return_value = mock_model_bound
    
    agent = ReviewAgent(mock_app_context)
    review = agent.generate_review(db, test_user.id)
    
    assert review.risk_summary == "No active holdings."
    assert "Standard SEBI caveat" in review.disclaimers
