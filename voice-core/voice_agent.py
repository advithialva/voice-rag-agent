# voice_agent.py
#
# Architecture: Gemini Native Audio (Live API)
#   Audio → gemini-2.5-flash-native-audio-preview-12-2025 → Audio
#   STT, reasoning, and TTS are all handled inside the Gemini model.
#   No Deepgram, Cartesia, or Vertex AI required.

import os
import asyncio
import time
import uuid
from typing import Any
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

from livekit import agents
from livekit.agents import AgentSession, RoomInputOptions, Agent
from livekit.agents.llm import function_tool
from livekit.plugins import google, noise_cancellation, silero

try:
    from backend.config.config_loader import config
    from backend.RAG.rag_chain import RAGManager
    from backend.lead_session import LeadSession
except ModuleNotFoundError:
    from config.config_loader import config
    from RAG.rag_chain import RAGManager
    from lead_session import LeadSession

load_dotenv(".env")

rag_manager = None
translator = None


def _resolve_call_id(ctx: agents.JobContext) -> str:
    room = getattr(ctx, "room", None)
    for attr in ("name", "sid", "id"):
        value = getattr(room, attr, None)
        if value:
            return f"{value}_{uuid.uuid4().hex[:8]}"
    return f"call_{int(time.time())}_{uuid.uuid4().hex[:8]}"


@function_tool
async def query_rag_database(question: str) -> str:
    """Query the configured knowledge base for information about products,
    services, pricing, or contact details.

    Args:
        question: The user's question about the configured products or services
    """
    global rag_manager
    if rag_manager is None:
        return "Knowledge base not available yet."
    return await rag_manager.query_rag_database(question)


class Assistant(Agent):
    def __init__(self, lead_session: LeadSession) -> None:
        self.lead_session = lead_session
        super().__init__(
            instructions="""You are a warm and friendly sales assistant.

Your personality:
- Conversational and natural — like talking to a helpful human colleague, not a robot
- Confident but never pushy
- Keep responses SHORT — 2 to 3 sentences max
- Never use bullet points or numbered lists — speak in natural flowing sentences
- Don't say "Certainly!", "Absolutely!", "Great question!" — just answer naturally
- Ask follow-up questions to understand what the customer needs

Your job:
- For ANY question about products, services, pricing, or contact details — ALWAYS call query_rag_database first
- Never make up product details — always use the knowledge base
- Understand what the customer needs and match it to an available product or service
- Offer to connect them with the sales team for a demo or purchase

LEAD COLLECTION BEHAVIOR:
- Do not ask for contact details early in the conversation.
- First answer the user's questions naturally and build engagement.
- Only begin lead qualification after detecting genuine business interest such as pricing inquiries, demo requests, deployment discussions, or implementation interest.
- Collect lead details gradually across the conversation.
- Prefer extracting information implicitly from user messages instead of directly asking.
- Never ask more than one lead-related question at a time.
- Never interrupt the natural conversational flow to collect data.
- If the user is casually exploring, prioritize helpful discussion over qualification.

Important style rules for voice:
- Summarize product info in 1-2 sentences instead of listing specs
- If you don't know something, say so honestly and offer the sales team contact
- Keep the conversation flowing — end with a question when appropriate
- If you're not sure what to ask next, call get_next_question to decide

Structured flow:
- Follow: greeting → name → contact → product → requirement → confirm when collecting details
- Ask only one lead question at a time and only after you answer the user's question
- Don't interrupt product discovery with lead questions; wait for a natural pause
- Use get_next_question to decide the next lead question when it feels appropriate""",
            tools=[query_rag_database]
        )

    @function_tool
    async def get_next_question(self) -> str:
        """Returns the next unanswered lead field to ask about, or an empty string if not ready."""
        return self.lead_session.next_missing_field()

async def entrypoint(ctx: agents.JobContext):
    global rag_manager
    global translator

    try:
        config.validate_required_keys([
            "agent.models.llm.model",
            "agent.rag.vectorstore_path",
        ])
    except ValueError as e:
        print(f"Configuration error: {e}")
        return

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("Missing GOOGLE_API_KEY in .env")
        print("Get it from: https://aistudio.google.com → Get API Key")
        return

    # Start RAG loading in background immediately
    rag_manager = RAGManager()
    rag_init_task = asyncio.create_task(rag_manager.initialize_rag(config))

    llm_config = config.get("agent.models.llm", {})
    model_name = llm_config.get("model", "gemini-2.5-flash-native-audio-preview-12-2025")
    voice_name = llm_config.get("voice", "Aoede")
    language = llm_config.get("language", "en-US")
    translation_config = config.get("agent.translation", {})
    translation_enabled = translation_config.get("enabled", True)
    translation_model = translation_config.get("model", "gemini-2.5-flash")
    translation_temperature = translation_config.get("temperature", 0.0)

    print(f"🎙  Model : {model_name}")
    print(f"🔊  Voice : {voice_name}")
    print(f"Language: {language}")

    # Single model handles STT + reasoning + TTS via Gemini Live API
    realtime_model = google.realtime.RealtimeModel(
        model=model_name,
        voice=voice_name,
        api_key=api_key,
        language=language,
        temperature=0.8,
    )

    if translation_enabled:
        translator = ChatGoogleGenerativeAI(
            model=translation_model,
            temperature=translation_temperature,
            max_retries=2,
        )

    translation_tasks: list[asyncio.Task] = []

    vad = silero.VAD.load()

    session = AgentSession(
        llm=realtime_model,
        vad=vad,
    )

    call_id = _resolve_call_id(ctx)
    lead_session = LeadSession(call_id=call_id)

    async def translate_to_english(text: str) -> str | None:
        if translator is None:
            return None
        prompt = (
            "Translate the following text to English. "
            "Return only the English translation, no extra words.\n\n"
            f"{text}"
        )
        try:
            result = await translator.ainvoke([HumanMessage(content=prompt)])
        except Exception as exc:
            print(f"Translation error: {exc}")
            return None

        content = getattr(result, "content", None)
        return content.strip() if isinstance(content, str) and content.strip() else None

    def needs_translation(text: str) -> bool:
        return any((ord(ch) > 127 and ch.isalpha()) for ch in text)

    async def attach_translation(entry: dict[str, Any], text: str) -> None:
        translated = await translate_to_english(text)
        if translated and translated != text:
            entry["translation_en"] = translated
            lead_session.apply_translation_update(translated)

    def handle_conversation_item(event) -> None:
        item = event.item
        if getattr(item, "type", None) != "message":
            return
        role = getattr(item, "role", None) or "unknown"
        text = getattr(item, "text_content", None)
        if not text:
            content = getattr(item, "content", [])
            text_parts = [part for part in content if isinstance(part, str)]
            text = "\n".join(text_parts).strip() if text_parts else ""
        if not text:
            return
        entry = lead_session.add_transcript(
            role=role,
            text=text,
            timestamp=getattr(item, "created_at", None),
        )
        if translation_enabled and role == "user" and needs_translation(text):
            translation_tasks.append(asyncio.create_task(attach_translation(entry, text)))

    async def finalize_transcript() -> None:
        if translation_tasks:
            await asyncio.gather(*translation_tasks, return_exceptions=True)
        print("\nLead session ended.")
        print(lead_session.as_dict())
        print("\nTranscript:")
        for entry in lead_session.lead.transcript:
            line = f"{entry['role']}: {entry['text']}"
            if "translation_en" in entry:
                line += f" [en: {entry['translation_en']}]"
            print(line)

    def handle_close(event) -> None:
        asyncio.create_task(finalize_transcript())

    session.on("conversation_item_added", handle_conversation_item)
    session.on("close", handle_close)

    room_input_options = RoomInputOptions()
    if config.get("agent.voice_processing.noise_cancellation", False):
        room_input_options.noise_cancellation = noise_cancellation.BVC()

    assistant = Assistant(lead_session)

    await session.start(
        room=ctx.room,
        agent=assistant,
        room_input_options=room_input_options,
    )

    print(f"\n{config.get('agent.name', 'Assistant')} is starting up...")
    print("Press [Ctrl+B] to switch to Text mode\n")

    await session.generate_reply(
        instructions="Greet the caller warmly in one short sentence and ask how you can help. One sentence only, natural and friendly."
    )

    try:
        await asyncio.wait_for(rag_init_task, timeout=65.0)
    except asyncio.TimeoutError:
        print("RAG initialization taking longer than expected. Continuing without RAG.")

    print("Agent is fully ready!")

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))