"""Onboarding tools: user profile management.

Note: manage_workspaces and ptc_agent are registered as direct flash tools
via SECRETARY_TOOLS in flash/agent.py. They are NOT included here to avoid
duplicate tool registration which causes create_agent to drop them.
"""

from src.tools.user_profile import USER_PROFILE_TOOLS

ONBOARDING_TOOLS = [*USER_PROFILE_TOOLS]

__all__ = [
    "ONBOARDING_TOOLS",
]
