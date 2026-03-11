from __future__ import annotations
import threading, time, logging, sys, os
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

PORT = 57892
log_lines: list[dict] = []

class UILogHandler(logging.Handler):
    def emit(self, record):
        log_lines.append({
            "time": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
            "level": record.levelname,
            "msg": record.getMessage(),
        })
        if len(log_lines) > 200:
            log_lines.pop(0)

logging.getLogger().addHandler(UILogHandler())

def start_api():
    os.chdir(BASE_DIR)
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))
    import uvicorn
    from api.server import app as fastapi_app, set_log_store
    set_log_store(log_lines)
    uvicorn.run(fastapi_app, host="127.0.0.1", port=PORT, log_level="debug", timeout_keep_alive=300)

def wait_for_api(timeout=15):
    import socket
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=1): return True
        except OSError: time.sleep(0.2)
    return False

class Api:
    def pick_files(self, file_types=("All files (*.*)",)):
        try:
            import webview
            result = window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=True, file_types=file_types)
            return list(result) if result else []
        except: return []

if __name__ == "__main__":
    import webview
    logger.info("LocalMind starting...")
    threading.Thread(target=start_api, daemon=True).start()
    logger.info("Waiting for API server...")
    if not wait_for_api():
        logger.error("API failed to start"); sys.exit(1)
    logger.info(f"API ready on port {PORT}")
    api = Api()
    window = webview.create_window(
        "LocalMind", f"http://127.0.0.1:{PORT}/",
        js_api=api, width=1280, height=820, min_size=(900,600)
    )
    webview.start(debug=False)
