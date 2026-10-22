# ragchain.py updated

import asyncio
import os
import re
from functools import partial
from typing import Optional, List

from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, AIMessage


class RAGManager:
    def __init__(self):
        self.llm: Optional[ChatGoogleGenerativeAI] = None
        self.retriever = None
        self.vectorstore: Optional[FAISS] = None
        self.rag_initialized = asyncio.Event()
        self._initialization_lock = asyncio.Lock()
        self.chat_history: List = []
        self._product_list_cache: Optional[str] = None  # Cache so we don't recompute every query
        self._category_list_cache: list[str] = []

    def _catalog_count(self) -> int:
        if not self._product_list_cache:
            return 0
        lines = [
            line
            for line in self._product_list_cache.splitlines()
            if line.strip().startswith("-")
        ]
        return len(lines)

    def _compact_answer(self, answer: str) -> str:
        text = answer.strip()
        if not text:
            return answer

        needs_compact = "\n" in text or len(text) > 350
        if not needs_compact:
            return text

        lines = []
        for line in text.splitlines():
            if not line.strip():
                continue
            cleaned = re.sub(r"^[^A-Za-z0-9]+", "", line).strip()
            if cleaned:
                lines.append(cleaned)

        merged = " ".join(lines)
        merged = re.sub(r"\s+", " ", merged).strip()
        if not merged:
            return text

        sentences = re.split(r"(?<=[.!?])\s+", merged)
        if len(sentences) > 2:
            merged = " ".join(sentences[:2]).strip()

        words = merged.split()
        if len(words) > 45:
            merged = " ".join(words[:45]).rstrip(",") + "..."

        if len(merged) > 350:
            merged = merged[:347].rstrip() + "..."

        return merged

    async def initialize_rag(self, config) -> None:
        async with self._initialization_lock:
            if self.rag_initialized.is_set():
                return

            print("Pre-loading RAG system...")

            rag_config = config.get("agent.rag", {})
            index_path = rag_config.get("vectorstore_path")
            embedding_model_name = rag_config.get("embedding_model", "BAAI/bge-m3")
            retrieval_k = rag_config.get("retrieval_k", 6)

            if not index_path:
                raise ValueError("Missing vectorstore_path in configuration")

            creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if creds_path:
                print(f"RAG LLM: using service account credentials ({creds_path})")
            else:
                print("RAG LLM: no service account found")

            try:
                self.vectorstore = await asyncio.wait_for(
                    self._load_vectorstore_async(index_path, embedding_model_name),
                    timeout=60.0
                )

                self.llm = ChatGoogleGenerativeAI(
                    model=rag_config.get("llm_model", "gemini-2.5-flash"),
                    temperature=0.1,
                    max_retries=3,
                )

                self.retriever = self.vectorstore.as_retriever(
                    search_type="similarity",
                    search_kwargs={"k": retrieval_k, "fetch_k": min(20, retrieval_k * 3)}
                )

                # Build and cache the product list once at startup from metadata
                self._product_list_cache = self._build_product_list_from_metadata()
                self._category_list_cache = self._build_category_list_from_products()

                self.rag_initialized.set()
                print("RAG system pre-loaded and ready!")

            except asyncio.TimeoutError:
                print("RAG initialization timed out.")
                self.rag_initialized.set()
            except Exception as e:
                print(f"RAG initialization error: {e}")
                self.rag_initialized.set()

    def _build_product_list_from_metadata(self) -> str:
        """
        Scan all documents in the FAISS index and extract unique product/service
        names directly from their metadata. Returns a formatted string like:
          - Biometric Authentication System (product)
          - Example service (service)
        This is called ONCE at startup and cached — zero cost at query time.
        """
        if self.vectorstore is None:
            return "product and service catalog unavailable"

        try:
            # FAISS stores all docs in its docstore — we can iterate them directly
            all_docs = self.vectorstore.docstore._dict.values()

            seen = set()
            entries = []

            for doc in all_docs:
                name = doc.metadata.get("name", "").strip()
                entry_type = doc.metadata.get("type", "").strip()

                # Skip contact info, general chunks, and empty names
                if not name or entry_type in ("contact_info", "general") or name == "Unknown":
                    continue

                key = name.lower()
                if key not in seen:
                    seen.add(key)
                    label = f"- {name} ({entry_type})" if entry_type else f"- {name}"
                    entries.append(label)

            if not entries:
                return "product and service catalog unavailable"

            return "\n".join(sorted(entries))

        except Exception as e:
            print(f"Warning: could not build product list from metadata: {e}")
            return "product and service catalog unavailable"

    def _build_category_list_from_products(self) -> list[str]:
        if not self._product_list_cache:
            return []

        keyword_map = {
            "sensor": "Sensors",
            "development board": "Development boards",
            "data logger": "Data loggers",
            "industrial io": "Industrial IO",
            "plc": "PLC and edge controllers",
            "gateway": "Gateways",
            "converter": "Converters and adapters",
            "relay": "Relay and IO modules",
            "programmer": "Programmers",
            "starter kit": "Starter kits",
        }

        counts = {label: 0 for label in keyword_map.values()}
        for line in self._product_list_cache.splitlines():
            if not line.strip().startswith("-"):
                continue
            name = line.lstrip("- ").strip().lower()
            for keyword, label in keyword_map.items():
                if keyword in name:
                    counts[label] += 1

        ranked = sorted(
            ((label, count) for label, count in counts.items() if count > 0),
            key=lambda item: item[1],
            reverse=True,
        )
        return [label for label, _count in ranked[:5]]

    async def _load_vectorstore_async(self, index_path: str, embedding_model_name: str) -> FAISS:
        print(f"📚 Loading FAISS vector store from: {index_path}")

        embedding_model = await asyncio.get_event_loop().run_in_executor(
            None,
            partial(HuggingFaceEmbeddings, model_name=embedding_model_name)
        )

        vectorstore = await asyncio.get_event_loop().run_in_executor(
            None,
            partial(
                FAISS.load_local,
                index_path,
                embeddings=embedding_model,
                allow_dangerous_deserialization=True
            )
        )

        print("✅ Vector store loaded.")
        return vectorstore

    def _build_standalone_question(self, question: str) -> str:
        """
        Build a context-aware question using chat history WITHOUT an extra LLM call.
        Simply appends the last user question as context if the current question
        is a follow-up (short or contains pronouns like 'it', 'that', 'this').
        Fast and free — no API call needed.
        """
        followup_triggers = ["it", "that", "this", "its", "their", "they", "more",
                             "tell me more", "what about", "and", "also", "same"]

        words = question.lower().strip().split()
        is_followup = (
            len(words) <= 6 or
            any(w in followup_triggers for w in words[:3])
        )

        if is_followup and self.chat_history:
            last_user_msg = ""
            for msg in reversed(self.chat_history):
                if isinstance(msg, HumanMessage):
                    last_user_msg = msg.content
                    break
            if last_user_msg:
                return f"{last_user_msg} — {question}"

        return question

    def _is_product_list_question(self, question: str) -> bool:
        """
        Detect if the user is asking how many products/services are available,
        or asking for a full list of them.
        """
        q = question.lower().strip()
        list_triggers = [
            "how many", "list all", "all products", "all services",
            "what products", "what services", "show all", "tell me all",
            "full list", "complete list", "what do you offer",
            "what do you sell", "what can you do"
        ]
        return any(trigger in q for trigger in list_triggers)

    def _is_category_question(self, question: str) -> bool:
        q = question.lower().strip()
        category_triggers = [
            "category", "categories", "types", "type of products", "product types",
        ]
        return any(trigger in q for trigger in category_triggers)

    async def query_rag_database(self, question: str) -> str:
        try:
            await asyncio.wait_for(self.rag_initialized.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            return "RAG system is still initializing. Please try again in a moment."

        if self.llm is None or self.retriever is None:
            return "I apologize, but the knowledge base is currently unavailable."

        if not question or len(question.strip()) < 2:
            return "Please provide a more specific question."

        try:
            if self._is_product_list_question(question):
                count = self._catalog_count()
                if count:
                    return (
                        f"We have about {count} products and services in our catalog. "
                        "Tell me the category or use-case and I can narrow it down."
                    )
                return (
                    "We have a broad catalog of products and services. "
                    "Tell me the category or use-case and I can narrow it down."
                )

            if self._is_category_question(question):
                if self._category_list_cache:
                    categories = ", ".join(self._category_list_cache[:-1])
                    if categories:
                        categories = f"{categories}, and {self._category_list_cache[-1]}"
                    else:
                        categories = self._category_list_cache[-1]
                    return (
                        f"We typically group our offerings into areas like {categories}. "
                        "Which of those is closest to what you need?"
                    )
                return (
                    "We cover a range of product and service categories. "
                    "Tell me your use-case and I can narrow it down."
                )

            # Step 1: Build context-aware query
            retrieval_query = self._build_standalone_question(question)

            # Step 2: Retrieve docs
            docs = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, self.retriever.invoke, retrieval_query
                ),
                timeout=5.0
            )
            context = "\n\n".join([doc.page_content for doc in docs])

            # Step 3: Build prompt and invoke LLM
            try:
                from backend.prompts import MASTER_PROMPT
                answer_prompt = MASTER_PROMPT
            except ImportError:
                answer_prompt = ChatPromptTemplate.from_messages([
                    ("system", "You are a configured organization assistant. Answer using ONLY this context:\n\n{context}"),
                    MessagesPlaceholder(variable_name="chat_history"),
                    ("human", "{question}"),
                ])

            answer_chain = answer_prompt | self.llm | StrOutputParser()

            final_answer = await asyncio.wait_for(
                answer_chain.ainvoke({
                    "context": context,
                    "question": question,
                    "chat_history": self.chat_history,
                }),
                timeout=15.0
            )

            final_answer = self._compact_answer(final_answer)

            # Step 5: Save to history
            if final_answer and len(final_answer.strip()) > 5:
                self.chat_history.append(HumanMessage(content=question))
                self.chat_history.append(AIMessage(content=final_answer))
                if len(self.chat_history) > 20:
                    self.chat_history = self.chat_history[-20:]

            return final_answer

        except asyncio.TimeoutError:
            return "The query is taking longer than expected. Please try again."
        except Exception as e:
            print(f"⚠️ RAG query error: {e}")
            return "I encountered an error while searching the knowledge base. Please try again."

    async def get_conversation_history(self) -> list:
        return self.chat_history

    async def clear_memory(self) -> None:
        self.chat_history = []
        print("🧹 Chat history cleared.")

    def is_ready(self) -> bool:
        return self.rag_initialized.is_set() and self.llm is not None