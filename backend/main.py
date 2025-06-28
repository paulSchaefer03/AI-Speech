from fastapi import FastAPI, UploadFile, File, Form
import shutil
import uuid
from fastapi.middleware.cors import CORSMiddleware
from backend.transcription import transcribe


app = FastAPI(title="Medizinische ASR API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],  # oder ["*"] für dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/transcribe")
async def transcribe_audio(model_name: str = Form(...), file: UploadFile = File(...)):
    temp_path = f"/tmp/{uuid.uuid4()}.wav"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    result = transcribe(model_name, temp_path)
    return {"steps": result}

@app.get("/api/models")
def list_models():
    return {
        "models": [
            "Whisper tiny",
            "Whisper base",
            "Whisper medium",
            "Whisper large-v3",
            "SpeechBrain CRDNN",
            "MultiMed Whisper"
        ]
    }
