"""LocalMind FastAPI backend."""

from __future__ import annotations
import json, uuid, shutil, logging, os, importlib.util, sys
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, StreamingResponse, Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent.parent
UI_DIR = BASE_DIR / "ui"
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
SETTINGS_FILE = DATA_DIR / "settings.json"
DATA_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)

# Ensure BASE_DIR is in sys.path so core/ is importable
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

app = FastAPI(title="LocalMind", docs_url=None)
_log_store: list = []


def set_log_store(store: list):
    global _log_store
    _log_store = store


DEFAULT_SETTINGS = {
    "ollama_url": "http://localhost:11434",
    "model": "llama3",
    "vision_model": "yolov8n",
    "ocr_languages": ["en"],
    "theme": "dark",
}


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return {**DEFAULT_SETTINGS, **json.loads(SETTINGS_FILE.read_text())}
        except:
            pass
    return DEFAULT_SETTINGS.copy()


def save_settings(d: dict):
    s = load_settings()
    s.update(d)
    SETTINGS_FILE.write_text(json.dumps(s, indent=2))


@app.get("/")
def serve_ui():
    return FileResponse(UI_DIR / "index.html")


@app.get("/api/settings")
def get_settings():
    return load_settings()


@app.post("/api/settings")
def update_settings(data: dict):
    save_settings(data)
    return {"ok": True}


@app.get("/api/logs")
def get_logs():
    return _log_store[-100:]


@app.get("/api/health")
def health():
    import socket

    s = load_settings()
    url = s.get("ollama_url", "http://localhost:11434")
    host = url.replace("http://", "").replace("https://", "").split(":")[0]
    try:
        port = int(url.split(":")[-1])
    except:
        port = 11434
    try:
        with socket.create_connection((host, port), timeout=2):
            ollama_ok = True
    except:
        ollama_ok = False
    return {"status": "ok", "ollama": ollama_ok, "version": "1.0.0"}


# ── Chat ──────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    messages: list[dict]
    model: Optional[str] = None
    ollama_url: Optional[str] = None


@app.post("/api/chat")
def chat_stream(req: ChatRequest):
    s = load_settings()
    model = req.model or s["model"]
    url = req.ollama_url or s["ollama_url"]
    from core.chat import stream_chat

    def gen():
        for token in stream_chat(req.messages, model, url):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


# ── Documents ─────────────────────────────────────────────────────────────────
_doc_store: dict[str, dict] = {}


@app.post("/api/docs/upload")
async def upload_doc(file: UploadFile = File(...)):
    dest = UPLOADS_DIR / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    from core.documents import extract_text, chunk_text

    text = extract_text(dest)
    chunks = chunk_text(text)
    doc_id = str(uuid.uuid4())[:8]
    _doc_store[doc_id] = {
        "name": file.filename,
        "chunks": chunks,
        "path": str(dest),
        "char_count": len(text),
    }
    logger.info(f"Uploaded: {file.filename} chunks={len(chunks)}")
    return {
        "id": doc_id,
        "name": file.filename,
        "chunks": len(chunks),
        "chars": len(text),
    }


@app.post("/api/docs/paste")
def paste_text(data: dict):
    text = data.get("text", "")
    name = data.get("name", "Pasted text")
    if not text.strip():
        raise HTTPException(400, "No text provided")
    from core.documents import chunk_text

    chunks = chunk_text(text)
    doc_id = str(uuid.uuid4())[:8]
    _doc_store[doc_id] = {
        "name": name,
        "chunks": chunks,
        "path": None,
        "char_count": len(text),
    }
    return {"id": doc_id, "name": name, "chunks": len(chunks), "chars": len(text)}


@app.get("/api/docs")
def list_docs():
    return [
        {
            "id": k,
            "name": v["name"],
            "chunks": len(v["chunks"]),
            "chars": v["char_count"],
        }
        for k, v in _doc_store.items()
    ]


@app.delete("/api/docs/{doc_id}")
def delete_doc(doc_id: str):
    if doc_id not in _doc_store:
        raise HTTPException(404, "Not found")
    d = _doc_store.pop(doc_id)
    if d["path"]:
        try:
            Path(d["path"]).unlink()
        except:
            pass
    return {"ok": True}


class DocAskRequest(BaseModel):
    query: str
    doc_ids: list[str] = []
    history: list[dict] = []
    model: Optional[str] = None
    ollama_url: Optional[str] = None


@app.post("/api/docs/ask")
def doc_ask(req: DocAskRequest):
    try:
        s = load_settings()
        model = req.model or s["model"]
        url = req.ollama_url or s["ollama_url"]
        ids = req.doc_ids or list(_doc_store.keys())
        if not ids:
            raise HTTPException(400, "No documents loaded")
        all_chunks, names = [], []
        for doc_id in ids:
            if doc_id in _doc_store:
                all_chunks.extend(_doc_store[doc_id]["chunks"])
                names.append(_doc_store[doc_id]["name"])
        logger.info(
            f"Doc ask: model={model} ollama={url} docs={names} chunks={len(all_chunks)}"
        )
        from core.documents import find_relevant_chunks, stream_answer

        relevant = find_relevant_chunks(all_chunks, req.query)

        def gen():
            try:
                for token in stream_answer(
                    req.query, relevant, req.history, model, url, names
                ):
                    yield f"data: {json.dumps({'token': token})}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.error(f"Stream error: {e}", exc_info=True)
                yield f"data: {json.dumps({'token': f'[Error: {str(e)}]'})}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Doc ask failed: {e}", exc_info=True)
        raise HTTPException(500, str(e))


# ── Vision ────────────────────────────────────────────────────────────────────
@app.post("/api/vision/detect")
async def vision_detect(task: str = "yolo", file: UploadFile = File(...)):
    s = load_settings()
    dest = UPLOADS_DIR / f"_vision_{uuid.uuid4().hex[:8]}_{file.filename}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        if task == "yolo":
            from core.vision import run_yolo

            return run_yolo(str(dest), s.get("vision_model", "yolov8n"))
        elif task == "ocr":
            from core.vision import run_ocr

            return run_ocr(str(dest), s.get("ocr_languages", ["en"]))
        elif task == "face":
            from core.vision import run_face_detection

            return run_face_detection(str(dest))
        else:
            raise HTTPException(400, f"Unknown task: {task}")
    finally:
        try:
            dest.unlink()
        except:
            pass
