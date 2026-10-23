# Voice RAG Agent: A Voice Sales Assistant Powered by Your Own Documents

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-API-green.svg)
![Next.js](https://img.shields.io/badge/Next.js-Dashboard-black.svg)
![LiveKit](https://img.shields.io/badge/LiveKit-Realtime_Voice-purple.svg)
![Gemini](https://img.shields.io/badge/Gemini-Native_Audio-red.svg)
![FAISS](https://img.shields.io/badge/FAISS-Vector_Search-lightgrey.svg)

Voice RAG Agent is a real-time voice assistant that talks to customers and answers product and service questions from a knowledge base. It comes with a web dashboard so the knowledge base can be edited and re-indexed without touching code.

It is designed for teams who want a voice assistant that speaks from their own product documents.

---

## ✨ Key Features

- 🎙️ Real-time voice conversations through a LiveKit worker
- ⚡ Single speech-to-speech model (Gemini native audio) handling listening, reasoning and speaking in one step
- 🔇 Background noise cancellation on the audio stream
- 📚 Retrieval-Augmented Generation (RAG) over a folder-based knowledge base
- 🧩 Product-aware chunking: every chunk keeps its product metadata, so a question about one product is answered from that product's document
- 🔄 On-demand re-indexing after documents are edited or added
- 🗂️ Knowledge-base dashboard to browse, create, edit, save, publish and re-index documents
- 🧾 In-call lead qualification that collects relevant details during the conversation
- 🕘 Version history for published knowledge-base changes
- ⚙️ Models, prompts, voice and retrieval settings controlled from one config file

---

## 💻 Tech Stack

| Category | Technologies |
|---|---|
| Voice runtime | LiveKit Agents · Python |
| Speech + LLM | Gemini native audio model |
| Retrieval | FAISS · multilingual sentence embeddings (BGE-M3) |
| LLM orchestration | LangChain |
| Knowledge-base API | FastAPI · Uvicorn |
| Dashboard | Next.js · React · TypeScript |

---

## 📁 Project Structure

```
voice-rag-agent
├─ voice-core/                  # Voice application and knowledge-base API
│  ├─ agents/                   # Agent definitions
│  ├─ RAG/                      # Retrieval chain
│  ├─ config/                   # Config file and loader
│  ├─ knowledge_base/           # Your source documents (git-ignored, not included)
│  ├─ KMS/                      # Version history and logs (git-ignored)
│  ├─ voice_agent.py            # Entry point for the voice worker
│  ├─ kb_admin.py               # Knowledge-base admin API
│  ├─ data_ingestion.py         # Chunking and index building
│  ├─ call_stages.py            # Conversation stage logic
│  ├─ prompts.py                # System prompts
│  ├─ .env                      # Local credentials (not committed)
│  └─ requirements.txt
├─ kb-dashboard/                # Knowledge-base management UI
│  ├─ src/
│  │  ├─ app/                   # Pages and API routes
│  │  ├─ components/            # File tree, editor, publish bar
│  │  └─ lib/                   # API client and types
│  ├─ .env.local                 # Local dashboard configuration (not committed)
│  └─ package.json
└─ README.md
```

---

## 🔧 Requirements

You need your own accounts and credentials. None are included in this repository.

- **LiveKit project**: server URL, API key and API secret
- **Google Cloud project** with access to Gemini models
- **Knowledge-base documents** of your own as `.txt` files, organised in folders by product or service. The `knowledge_base/` folder is git-ignored, so it is not part of this repository and you need to create it yourself.

Software:

- Python 3.10 or newer
- Node.js 18 or newer and npm
- Enough disk space for the embedding model, which downloads on first run

---

## 🚀 Installation

### 🖥️ Voice Core Setup

1. **Clone and navigate**

```bash
git clone https://github.com/advithialva/voice-rag-agent.git
cd voice-rag-agent/voice-core
```

2. **Create a virtual environment**

```bash
python -m venv venv
source venv/bin/activate

# On Windows: venv\Scripts\activate
```

3. **Install dependencies**

```bash
pip install -r requirements.txt
```

4. **Create your environment file**

Create a `.env` file inside the `voice-core/` directory and add your credentials as described in the Environment Variables section below.

```env
# LiveKit connection
LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=

# Google Gemini Native Audio
GOOGLE_API_KEY=

# Optional: Google service-account credentials for RAG
GOOGLE_APPLICATION_CREDENTIALS=
```

5. **Update the config file**

Open `config/config.yaml` and set your own Google project and region. Set the LiveKit URL and credentials in `voice-core/.env`.

6. **Add your knowledge base**

Create `voice-core/knowledge_base/` and add your `.txt` documents in folders by product or service.

7. **Build the knowledge-base index**

```bash
python data_ingestion.py
```

The generated index is stored inside `knowledge_base/`, so it is git-ignored too.

### 🌐 Dashboard Setup

```bash
cd ../kb-dashboard
npm install
```

Create a `.env.local` file in `kb-dashboard/` and add:

```env
KB_ADMIN_API_BASE_URL=http://127.0.0.1:8090
```

---

## ▶️ Running the Project

Run each part in its own terminal.

**1. Knowledge-base API**

```bash
cd voice-core
uvicorn kb_admin:app --port 8090
```

**2. Dashboard**

```bash
cd kb-dashboard
npm run dev
```

The dashboard runs at `http://localhost:3000` and talks to the API on port 8090.

**3. Voice worker**

```bash
cd voice-core
python voice_agent.py dev
```

---

## ⚙️ Configuration

Behaviour is controlled from `voice-core/config/config.yaml`:

| Section | What it controls |
|---|---|
| `livekit` | Server URL and credentials |
| `agent` | Assistant name, instructions and voice model settings |
| `rag` | Index location, embedding model, number of chunks retrieved, answer model |
| `voice_processing` | Noise cancellation |

---

## 🧠 How the Knowledge Base Works

1. Documents in `knowledge_base/` are split into chunks.
2. Each chunk keeps a label for the product or service it came from.
3. Chunks are embedded and stored in a FAISS index.
4. During a call, the agent runs a retrieval tool for product and service questions and answers using the chunks it gets back.
5. After you edit documents in the dashboard, publish and re-index to refresh the index.

Keeping the product label on every chunk was important: without it, similar documents could get mixed up and a question about one product could be answered from another.

---

## 🛣️ Roadmap

- Telephony support (inbound and outbound calls)
- Automated retrieval evaluation
- Authentication for the dashboard

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes (`git commit -m 'Add your feature'`)
4. Push to the branch (`git push origin feature/your-feature`)
5. Open a Pull Request
