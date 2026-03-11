from __future__ import annotations
import logging
from pathlib import Path
from typing import Iterator
logger = logging.getLogger(__name__)

def extract_text(path: Path) -> str:
    suf = path.suffix.lower()
    if suf == ".pdf":
        try:
            import fitz
            doc = fitz.open(str(path))
            return "\n".join(p.get_text() for p in doc)
        except ImportError:
            return "[Install pymupdf: pip install pymupdf]"
    elif suf == ".docx":
        try:
            import docx
            return "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
        except ImportError:
            return "[Install python-docx: pip install python-docx]"
    else:
        return path.read_text(errors="ignore")

def chunk_text(text: str, size: int = 800, overlap: int = 100) -> list[str]:
    words = text.split()
    chunks, i = [], 0
    while i < len(words):
        chunks.append(" ".join(words[i:i+size]))
        i += size - overlap
    return chunks

def find_relevant_chunks(chunks: list[str], query: str, top_k: int = 4) -> list[str]:
    q_words = set(query.lower().split())
    scored = sorted(chunks, key=lambda c: len(q_words & set(c.lower().split())), reverse=True)
    return scored[:top_k]

def stream_answer(query: str, chunks: list[str], history: list[dict], model: str, ollama_url: str, sources: list[str]) -> Iterator[str]:
    import httpx, json
    context = "\n\n---\n\n".join(chunks[:4])
    src = ", ".join(sources) if sources else "pasted text"
    system = f"You are a helpful assistant. Answer questions based on these document excerpts from: {src}\n\n{context}\n\nIf the answer isn't in the excerpts, say so."
    messages = [{"role": "system", "content": system}] + history[-6:] + [{"role": "user", "content": query}]
    logger.info(f"Doc Q&A: model={model} chunks={len(chunks)}")
    with httpx.stream("POST", f"{ollama_url}/api/chat", json={"model": model, "messages": messages, "stream": True}, timeout=300) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line.strip(): continue
            try:
                chunk = json.loads(line)
                token = chunk.get("message", {}).get("content", "")
                if token: yield token
                if chunk.get("done"): break
            except json.JSONDecodeError: continue
