from __future__ import annotations

from typing import Any, Literal

from .architect_agent import get_architect_agent
from .backend_agent import get_backend_agent
from .dependency_agent import get_dependency_agent
from .frontend_agent import get_frontend_agent
from .pm_agent import get_pm_agent

AgentRole = Literal[
    "pm_agent",
    "architect_agent",
    "backend_agent",
    "frontend_agent",
    "dependency_agent",
]


class AgentFactory:
    """Simple role-to-getter factory used by the orchestrator."""

    def create_agent(self, role: AgentRole) -> Any:
        if role == "pm_agent":
            return get_pm_agent()
        if role == "architect_agent":
            return get_architect_agent()
        if role == "backend_agent":
            return get_backend_agent()
        if role == "frontend_agent":
            return get_frontend_agent()
        if role == "dependency_agent":
            return get_dependency_agent()
        raise ValueError(f"Unknown agent role: {role}")


def build_agent_factory() -> AgentFactory:
    return AgentFactory()


__all__ = [
    "AgentFactory",
    "build_agent_factory",
    "get_pm_agent",
    "get_architect_agent",
    "get_backend_agent",
    "get_frontend_agent",
    "get_dependency_agent",
]

