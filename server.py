from fastapi import FastAPI, WebSocket, UploadFile, File, Form
from fastapi.responses import PlainTextResponse, JSONResponse, FileResponse
from starlette.websockets import WebSocketDisconnect
import numpy as np
import cv2
from ultralytics import YOLO
import json
import os
from openai import OpenAI
import base64



client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

from datetime import datetime
import uvicorn

app = FastAPI()
model = YOLO("yolov8n.pt")




# =========================
# 1. YOLO 실시간 감지 WebSocket
# Unity WebSocket 주소:
# ws://PC아이피:9000/ws
# =========================

@app.post("/detect")
async def detect(image: UploadFile = File(...)):
    data = await image.read()

    npimg = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

    if img is None:
        return JSONResponse({"detections": []})

    results = model(img, conf=0.3, verbose=False)

    detections = []

    for r in results:
        for box in r.boxes:
            cls = int(box.cls[0])
            label = model.names[cls]

            if label not in ["person", "car", "bicycle"]:
                continue

            x1, y1, x2, y2 = box.xyxy[0].tolist()
            h, w, _ = img.shape

            detections.append({
                "label": label,
                "x": ((x1 + x2) / 2) / w,
                "y": ((y1 + y2) / 2) / h,
                "width": (x2 - x1) / w,
                "height": (y2 - y1) / h,
                "confidence": float(box.conf[0])
            })

    return JSONResponse({"detections": detections})


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    print("🔗 WebSocket 연결됨")

    try:
        while True:
            message = await ws.receive()

            if "text" in message:
                print("📩 text:", message["text"])
                continue

            if "bytes" not in message:
                continue

            data = message["bytes"]

            npimg = np.frombuffer(data, np.uint8)
            img = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

            if img is None:
                continue

            results = model(img, conf=0.3, verbose=False)

            detections = []

            for r in results:
                for box in r.boxes:
                    cls = int(box.cls[0])
                    label = model.names[cls]

                    if label not in ["person", "car", "bicycle"]:
                        continue

                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    h, w, _ = img.shape

                    detections.append({
                        "label": label,
                        "x": ((x1 + x2) / 2) / w,
                        "y": ((y1 + y2) / 2) / h,
                        "width": (x2 - x1) / w,
                        "height": (y2 - y1) / h,
                        "confidence": float(box.conf[0])
                    })

            await ws.send_text(json.dumps({"detections": detections}))

    except WebSocketDisconnect:
        print("🔌 WebSocket 정상 연결 종료")

    except Exception as e:
        print("⚠️ WebSocket 오류:", e)



# =========================
# 2. GPT Vision용 이미지 분석 테스트 API
# Unity HTTP 주소:
# http://PC아이피:9000/analyze
# =========================
@app.post("/analyze", response_class=PlainTextResponse)
async def analyze(image: UploadFile = File(...)):
    os.makedirs("captures", exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = f"captures/capture_{timestamp}.jpg"

    data = await image.read()

    with open(file_path, "wb") as f:
        f.write(data)

    print(f"📸 이미지 수신 완료: {file_path}, 크기: {len(data)} bytes")

    with open(file_path, "rb") as f:
        base64_image = base64.b64encode(f.read()).decode("utf-8")

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": """
당신은 프레데터 HUD 분석 AI이다.

다음 형식으로 출력하라.

대상:
행동:
위험도:
요약:

100자 이내
"""
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{base64_image}"
                    }
                ]
            }
        ]
    )

    return response.output_text


# =========================
# 3. 서버 상태 확인용
# 브라우저에서:
# http://PC아이피:9000/
# =========================
@app.get("/", response_class=PlainTextResponse)
async def root():
    return "YOLO + GPT Analyze Server Running"




# =========================
# 1. 음성인식기능구현
# =========================

@app.post("/stt", response_class=PlainTextResponse)
async def stt(audio: UploadFile = File(...)):
    os.makedirs("voices", exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = f"voices/voice_{timestamp}.wav"

    data = await audio.read()

    with open(file_path, "wb") as f:
        f.write(data)

    print(f"🎙 음성 수신 완료: {file_path}, 크기: {len(data)} bytes")

    with open(file_path, "rb") as f:
        transcript = client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=f,
            language="ko"
        )

    return transcript.text

# =========================
# 1. 채팅 기능
# =========================
@app.post("/chat", response_class=PlainTextResponse)
async def chat(message: str = Form(...)):
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=f"""
너는 HoloLens HUD AI 비서 '토요일'이다.
짧고 명확하게 한국어로 답하라.

사용자 질문:
{message}
"""
    )

    return response.output_text

# =========================
# 1. TTS 기능
# =========================

@app.post("/tts")
async def tts(message: str = Form(...)):
    os.makedirs("tts", exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = f"tts/answer_{timestamp}.mp3"

    with client.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice="nova",
        input=message
    ) as response:
        response.stream_to_file(file_path)

    return FileResponse(file_path, media_type="audio/mpeg", filename="answer.mp3")


# =========================
# 4. 서버 실행
# =========================
if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=9000
    )