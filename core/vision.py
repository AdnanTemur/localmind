from __future__ import annotations
import logging, base64
from pathlib import Path
logger = logging.getLogger(__name__)

def run_yolo(image_path: str, model_size: str = "yolov8n") -> dict:
    try:
        from ultralytics import YOLO
        import cv2
        model = YOLO(f"{model_size}.pt")
        results = model(image_path, verbose=False)
        r = results[0]
        detections = [{"label": r.names[int(b.cls)], "confidence": round(float(b.conf), 3), "box": [round(float(x),1) for x in b.xyxy[0].tolist()]} for b in r.boxes]
        _, buf = cv2.imencode(".jpg", r.plot())
        return {"ok": True, "detections": detections, "image_b64": base64.b64encode(buf).decode(), "model": model_size}
    except ImportError: return {"ok": False, "error": "Run: pip install ultralytics"}
    except Exception as e: return {"ok": False, "error": str(e)}

def run_ocr(image_path: str, languages: list[str] = ["en"]) -> dict:
    try:
        import easyocr
        reader = easyocr.Reader(languages, verbose=False)
        results = reader.readtext(image_path)
        texts = [{"text": t, "confidence": round(float(c), 3)} for _, t, c in results]
        return {"ok": True, "texts": texts, "full_text": " ".join(t["text"] for t in texts)}
    except ImportError: return {"ok": False, "error": "Run: pip install easyocr"}
    except Exception as e: return {"ok": False, "error": str(e)}

def run_face_detection(image_path: str) -> dict:
    try:
        import cv2, base64
        img = cv2.imread(image_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(30,30))
        for (x,y,w,h) in faces: cv2.rectangle(img,(x,y),(x+w,y+h),(0,200,100),2)
        _, buf = cv2.imencode(".jpg", img)
        return {"ok": True, "faces": [{"x":int(x),"y":int(y),"w":int(w),"h":int(h)} for x,y,w,h in faces], "count": len(faces), "image_b64": base64.b64encode(buf).decode()}
    except ImportError: return {"ok": False, "error": "Run: pip install opencv-python"}
    except Exception as e: return {"ok": False, "error": str(e)}
