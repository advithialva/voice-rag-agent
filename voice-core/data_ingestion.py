# data_ingestion.py
"""
Data Ingestion Pipeline for Voice RAG Knowledge Base
============================================================
- Product-aware chunking with rich metadata extraction
- Handles Products (###**Product Name**###) AND Services (###**Service Name**###)
- Contact info preserved as a single chunk
- Metadata: category, subcategory, brand, price, order_code, product_link, source_file
"""

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
import re
import os


# ─── Parse structured JSON-like metadata block ───────────────────────────────
def _extract_json_metadata(text: str) -> dict:
    """Extract metadata from the JSON-ish block inside product entries."""
    meta = {}
    match = re.search(r'\{([^}]+)\}', text, re.DOTALL)
    if not match:
        return meta

    block = match.group(1)
    # Parse key-value pairs tolerantly (handles missing commas, inconsistent quoting)
    for kv in re.finditer(r'"([^"]+)"\s*:\s*"([^"]*)"', block):
        key = kv.group(1).strip().lower().replace(" ", "_")
        value = kv.group(2).strip()
        meta[key] = value

    return meta


# ─── Split a document into product/service-level chunks ──────────────────────
def split_document_by_entries(text: str, source_file: str) -> list:
    """
    Split text on ###**Product Name**### or ###**Service Name**### headers.
    Each entry becomes one Document with rich metadata.
    """
    entry_pattern = r'#{2,3}\*\*(?:Product Name|Service Name)\*\*#{2,3}'
    parts = re.split(f'(?={entry_pattern})', text)

    docs = []
    for part in parts:
        part = part.strip()
        if not part or len(part) < 20:
            continue

        # Extract the entry name
        name_match = re.search(
            r'#{2,3}\*\*(?:Product Name|Service Name)\*\*#{2,3}:?\s*\n\s*(.+)',
            part
        )
        entry_name = name_match.group(1).strip() if name_match else "Unknown"

        # Determine type (product vs service)
        is_service = bool(re.search(r'Service Name', part[:100]))
        entry_type = "service" if is_service else "product"

        # Extract structured metadata from JSON block
        json_meta = _extract_json_metadata(part)

        # Derive category from file path
        category = _category_from_path(source_file)

        metadata = {
            "name": entry_name,
            "type": entry_type,
            "category": category,
            "subcategory": json_meta.get("sub-category", json_meta.get("sub_category", "")),
            "brand": json_meta.get("brand", ""),
            "price": json_meta.get("price", ""),
            "order_code": json_meta.get("order_code", json_meta.get("order_code", "")),
            "product_id": json_meta.get("product_id", ""),
            "product_link": json_meta.get("product_link", json_meta.get("product_link", "")),
            "source_file": os.path.basename(source_file),
        }

        # Clean the chunk text: remove the raw JSON block to reduce noise
        clean_text = re.sub(r'\{[^}]+\}', '', part).strip()
        clean_text = re.sub(r'\n{3,}', '\n\n', clean_text)

        docs.append(Document(page_content=clean_text, metadata=metadata))

    return docs


def _category_from_path(filepath: str) -> str:
    """Derive a category from the file's directory path."""
    filepath_lower = filepath.lower()
    if "sensor" in filepath_lower:
        return "sensors"
    elif "development board" in filepath_lower or "development_board" in filepath_lower:
        return "development boards"
    elif "industrial" in filepath_lower:
        return "industrial IO"
    elif "service" in filepath_lower:
        return "services"
    return "general"


# ─── Handle non-structured files (contact info, etc.) ────────────────────────
def handle_plain_text_file(text: str, source_file: str) -> list:
    """For files that don't follow the Product/Service header format."""
    filename_lower = os.path.basename(source_file).lower()

    if "contact" in filename_lower:
        return [Document(
            page_content=text.strip(),
            metadata={
                "name": "Contact Information",
                "type": "contact_info",
                "category": "company",
                "source_file": os.path.basename(source_file),
            }
        )]

    # For any other unstructured file, use recursive text splitting
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
        separators=["\n\n", "\n", ". ", " "]
    )
    chunks = splitter.create_documents(
        [text],
        metadatas=[{
            "name": "General Info",
            "type": "general",
            "category": _category_from_path(source_file),
            "source_file": os.path.basename(source_file),
        }]
    )
    return chunks


# ─── Large product entries: secondary splitting ──────────────────────────────
def split_large_chunks(docs: list, max_chunk_size: int = 1500) -> list:
    """
    If a product/service chunk exceeds max_chunk_size characters,
    split it into smaller overlapping sub-chunks while preserving metadata.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_chunk_size,
        chunk_overlap=200,
        separators=["\n###", "\n##", "\n\n", "\n- ", "\n", ". ", " "]
    )
    result = []
    for doc in docs:
        if len(doc.page_content) > max_chunk_size:
            sub_chunks = splitter.create_documents(
                [doc.page_content],
                metadatas=[doc.metadata]
            )
            for i, sub in enumerate(sub_chunks):
                sub.metadata = {**doc.metadata, "chunk_part": i + 1, "total_parts": len(sub_chunks)}
                result.append(sub)
        else:
            result.append(doc)
    return result


# ─── Load documents ──────────────────────────────────────────────────────────
def load_documents_from_directory(directory_path: str):
    loader = DirectoryLoader(
        path=directory_path,
        glob="**/*.txt",
        loader_cls=lambda p: TextLoader(p, encoding="utf-8"),
        show_progress=True
    )
    return loader.load()


# ─── Embedding Model ─────────────────────────────────────────────────────────
def get_embedding_model():
    model_kwargs = {'device': 'cpu'}
    encode_kwargs = {'batch_size': 8}
    return HuggingFaceEmbeddings(
        model_name="BAAI/bge-m3",
        model_kwargs=model_kwargs,
        encode_kwargs=encode_kwargs
    )


# ─── Main Pipeline ───────────────────────────────────────────────────────────
def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    directory_path = os.path.join(script_dir, "knowledge_base")

    def emit_progress(percent: int, label: str) -> None:
        percent = max(0, min(99, percent))
        print(f"PROGRESS: {percent} {label}", flush=True)

    # Step 1: Load raw documents
    documents = load_documents_from_directory(directory_path)
    emit_progress(5, "Loaded raw files")
    print(f"\n✅ Total raw files loaded: {len(documents)}")
    for i, doc in enumerate(documents, 1):
        print(f"  File {i}: {doc.metadata['source']}")

    # Step 2: Smart splitting — product/service aware + fallback for plain text
    entry_pattern = r'#{2,3}\*\*(?:Product Name|Service Name)\*\*#{2,3}'
    all_chunks = []
    total_docs = len(documents) or 1
    last_progress = 5
    for index, doc in enumerate(documents, 1):
        if re.search(entry_pattern, doc.page_content):
            chunks = split_document_by_entries(doc.page_content, doc.metadata.get("source", ""))
            all_chunks.extend(chunks)
        else:
            chunks = handle_plain_text_file(doc.page_content, doc.metadata.get("source", ""))
            all_chunks.extend(chunks)

        progress = 5 + int((index / total_docs) * 45)
        if progress > last_progress:
            emit_progress(progress, f"Split {index}/{total_docs}")
            last_progress = progress

    print(f"\n📦 Chunks after entry-level splitting: {len(all_chunks)}")
    emit_progress(55, "Entry split complete")

    # Step 3: Split oversized chunks
    all_chunks = split_large_chunks(all_chunks, max_chunk_size=1500)
    print(f"📦 Chunks after size-based splitting: {len(all_chunks)}")
    emit_progress(65, "Chunk sizing complete")

    # Step 4: Summary stats
    categories = {}
    for c in all_chunks:
        cat = c.metadata.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1
    print("\n📊 Chunks by category:")
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count}")

    # Show sample metadata
    print("\n📋 Sample chunk metadata (first 3):")
    for chunk in all_chunks[:3]:
        print(f"  Name: {chunk.metadata.get('name', 'N/A')}")
        print(f"  Type: {chunk.metadata.get('type', 'N/A')}")
        print(f"  Category: {chunk.metadata.get('category', 'N/A')}")
        print(f"  Price: {chunk.metadata.get('price', 'N/A')}")
        print(f"  Text preview: {chunk.page_content[:100]}...")
        print()

    # Step 5: Generate embeddings & save
    emit_progress(70, "Embedding start")
    embedding_model = get_embedding_model()
    db = FAISS.from_documents(all_chunks, embedding_model)
    emit_progress(90, "Embedding complete")

    faiss_path = os.path.join(directory_path, "faiss_index")
    db.save_local(faiss_path)
    print(f"✅ FAISS index saved to: {faiss_path}")
    print(f"✅ Total vectors stored: {len(all_chunks)}")
    emit_progress(95, "FAISS saved")


if __name__ == "__main__":
    main()
