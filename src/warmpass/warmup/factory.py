from warmpass.agents.factory import create_warmup_agent
from warmpass.agents.models import WarmupAgentType
from warmpass.warmup.service import WarmupService


def create_warmup_service(agent_type: WarmupAgentType) -> WarmupService:
    warmup_agent = create_warmup_agent(agent_type)
    return WarmupService(warmup_agent)
