from __future__ import annotations
import logging
from typing import Iterator
logger = logging.getLogger(__name__)

def stream_chat(messages: list[dict], model: str, ollama_url: str) -> Iterator[str]:
    import httpx, json
    url = f"{ollama_url}/api/chat"
    logger.info(f"Chat: model={model} messages={len(messages)}")
    with httpx.stream("POST", url, json={"model": model, "messages": messages, "stream": True}, timeout=300) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line.strip(): continue
            try:
                chunk = json.loads(line)
                token = chunk.get("message", {}).get("content", "")
                if token: yield token
                if chunk.get("done"): break
            except json.JSONDecodeError: continue
