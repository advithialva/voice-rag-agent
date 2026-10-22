# agents/assistant.py
from livekit.agents import Agent
from livekit.agents import llm

class Assistant(Agent):
    def __init__(self, rag_manager, config):
        self.rag_manager = rag_manager
        instructions = config.get("agent.instructions")
        super().__init__(instructions=instructions)

    @llm.tool()
    async def query_rag_database(self, question: str) -> str:
        """Query the configured knowledge base for information about products, services, or organization details.

        Args:
            question: The specific question to search for
        """
        return await self.rag_manager.query_rag_database(question)