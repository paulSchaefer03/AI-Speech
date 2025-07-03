from fastapi import FastAPI, UploadFile, File, Form, WebSocket, WebSocketDisconnect
import shutil
import uuid
import json
import asyncio
import base64
import io
import wave
import os
import tempfile
import time
import numpy as np
import torch
import whisper
from typing import Dict, Any
from fastapi.middleware.cors import CORSMiddleware
from backend.transcription import transcribe, transcribe_audio_chunk, multimed_model
from backend.vosk_transcription import get_vosk_stream_transcriber, cleanup_vosk_resources
from pydub import AudioSegment


        
app = FastAPI(title="Medizinische ASR API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
    "http://localhost:5173",
    "http://localhost:7860",
    "https://paul-schaefer-ms-7d75.tailf4012b.ts.net",
    ],
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
            "MultiMed Whisper",
            "Vosk German"
        ]
    }

# Dictionary für aktive WebSocket-Verbindungen
active_connections: dict[str, WebSocket] = {}

# Dictionary für Modell-Status
model_status = {
    "Whisper tiny": {"loaded": False, "loading": False},
    "Whisper base": {"loaded": False, "loading": False},
    "Whisper medium": {"loaded": False, "loading": False},
    "Whisper large-v3": {"loaded": False, "loading": False},
    "SpeechBrain CRDNN": {"loaded": True, "loading": False},  # Bereits geladen
    "MultiMed Whisper": {"loaded": bool(multimed_model), "loading": False},
    "Vosk German": {"loaded": False, "loading": False}
}

@app.get("/api/model-status/{model_name}")
def get_model_status(model_name: str):
    """Gibt den Ladestatus eines Modells zurück."""
    status = model_status.get(model_name, {"loaded": False, "loading": False})
    return status

@app.post("/api/preload-model")
async def preload_model(request: dict):
    """Lädt ein Modell vor, um die erste Transkription zu beschleunigen."""
    model_name = request.get("model_name")
    
    if model_name not in model_status:
        return {"success": False, "message": "Unbekanntes Modell"}
    
    if model_status[model_name]["loaded"]:
        return {"success": True, "message": "Modell bereits geladen"}
    
    if model_status[model_name]["loading"]:
        return {"success": False, "message": "Modell wird bereits geladen"}
    
    try:
        model_status[model_name]["loading"] = True
        
        if model_name.startswith("Whisper"):
            from backend.transcription import loaded_whisper_models
            model_id = model_name.split(" ")[1].lower()
            if model_id not in loaded_whisper_models:
                loaded_whisper_models[model_id] = whisper.load_model(model_id, device="cuda" if torch.cuda.is_available() else "cpu")
            model_status[model_name]["loaded"] = True
            
        elif model_name == "Vosk German":
            from backend.vosk_transcription import get_vosk_transcriber
            get_vosk_transcriber()  # Lädt das Modell
            model_status[model_name]["loaded"] = True
            
        model_status[model_name]["loading"] = False
        return {"success": True, "message": "Modell erfolgreich geladen"}
        
    except Exception as e:
        model_status[model_name]["loading"] = False
        return {"success": False, "message": f"Fehler beim Laden: {str(e)}"}

# Dictionary für aktive WebSocket-Verbindungen
active_connections: dict[str, WebSocket] = {}

@app.websocket("/api/transcribe-live")
async def transcribe_live(websocket: WebSocket):
    await websocket.accept()
    connection_id = str(uuid.uuid4())
    active_connections[connection_id] = websocket
    print(f"WebSocket connected: {connection_id}")
    
    try:
        while True:
            # Empfange Nachricht vom Frontend
            print(f"Waiting for message...")
            message = await websocket.receive_text()
            data = json.loads(message)
            print(f"Received message type: {data.get('type')}")
            
            if data["type"] == "audio_chunk":
                # Dekodiere Base64-Audio
                audio_data = base64.b64decode(data["audio"])
                model_name = data["model"]
                print(f"Processing audio chunk: {len(audio_data)} bytes, model: {model_name}")
                
                temp_files_to_cleanup = []
                
                try:
                    # Verwende die robuste Audio-Verarbeitung
                    processed_audio_path = process_audio_chunk_robust(audio_data, connection_id)
                    
                    if processed_audio_path is None:
                        raise Exception("Konnte Audio-Chunk nicht verarbeiten - alle Fallbacks fehlgeschlagen")
                    
                    temp_files_to_cleanup.append(processed_audio_path)
                    print(f"Audio processing successful: {processed_audio_path}")
                    
                    # Transkribiere den Chunk
                    print(f"Starting transcription with model: {model_name}")
                    transcription = transcribe_audio_chunk(model_name, processed_audio_path, quick_mode=True)
                    print(f"Transcription result: {transcription}")
                    
                    # Sende Ergebnis zurück
                    await websocket.send_text(json.dumps({
                        "type": "transcription",
                        "text": transcription,
                        "chunk_id": data.get("chunk_id", "")
                    }))
                    
                except Exception as e:
                    print(f"Transcription error: {e}")
                    import traceback
                    traceback.print_exc()
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"Fehler bei der Transkription: {str(e)}"
                    }))
                finally:
                    # Temporäre Dateien löschen
                    for path in temp_files_to_cleanup:
                        if os.path.exists(path):
                            try:
                                os.remove(path)
                            except:
                                pass
            
            elif data["type"] == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket Fehler: {e}")
    finally:
        # Verbindung aufräumen
        if connection_id in active_connections:
            del active_connections[connection_id]

# Lazy loading für Vosk-Modell
def ensure_vosk_loaded():
    """Stelle sicher, dass das Vosk-Modell geladen ist."""
    if not model_status["Vosk German"]["loaded"] and not model_status["Vosk German"]["loading"]:
        model_status["Vosk German"]["loading"] = True
        try:
            from backend.vosk_transcription import get_vosk_transcriber
            get_vosk_transcriber()  # Lädt das Modell
            model_status["Vosk German"]["loaded"] = True
        except Exception as e:
            print(f"Fehler beim Laden des Vosk-Modells: {e}")
        finally:
            model_status["Vosk German"]["loading"] = False

def process_audio_chunk_robust(audio_data: bytes, connection_id: str) -> str:
    """
    Robuste Audio-Chunk-Verarbeitung mit mehreren Fallback-Strategien
    """
    temp_files = []
    
    try:
        # Versuche verschiedene Ansätze für die Audio-Verarbeitung
        timestamp = uuid.uuid4().hex[:8]
        
        # 1. Direkter Versuch als WebM
        temp_webm = f"/tmp/live_{connection_id}_{timestamp}.webm"
        temp_files.append(temp_webm)
        
        with open(temp_webm, "wb") as f:
            f.write(audio_data)
        
        print(f"Wrote {len(audio_data)} bytes to {temp_webm}")
        
        # 2. Versuche mit pydub zu konvertieren
        temp_wav = f"/tmp/live_{connection_id}_{timestamp}.wav"
        temp_files.append(temp_wav)
        
        try:
            print("Trying pydub conversion...")
            audio_segment = AudioSegment.from_file(temp_webm)
            # Konvertiere zu Mono, 16kHz
            audio_segment = audio_segment.set_channels(1).set_frame_rate(16000)
            audio_segment.export(temp_wav, format="wav")
            print(f"Pydub conversion successful: {temp_wav}")
            return temp_wav
            
        except Exception as pydub_error:
            print(f"Pydub failed: {pydub_error}")
            
            # 3. Versuche direkten ffmpeg-Aufruf
            try:
                import subprocess
                temp_wav_ffmpeg = f"/tmp/live_{connection_id}_{timestamp}_ffmpeg.wav"
                temp_files.append(temp_wav_ffmpeg)
                
                print("Trying direct ffmpeg conversion...")
                result = subprocess.run([
                    'ffmpeg', '-y', '-f', 'webm', '-i', temp_webm,
                    '-ar', '16000', '-ac', '1', '-f', 'wav', temp_wav_ffmpeg
                ], capture_output=True, text=True, timeout=10)
                
                if result.returncode == 0 and os.path.exists(temp_wav_ffmpeg):
                    print(f"FFmpeg conversion successful: {temp_wav_ffmpeg}")
                    return temp_wav_ffmpeg
                else:
                    print(f"FFmpeg failed with return code {result.returncode}")
                    print(f"FFmpeg stderr: {result.stderr}")
                    
            except Exception as ffmpeg_error:
                print(f"Direct ffmpeg failed: {ffmpeg_error}")
                
                # 4. Fallback: Versuche als WAV zu interpretieren
                try:
                    print("Trying to treat as WAV directly...")
                    temp_direct_wav = f"/tmp/live_{connection_id}_{timestamp}_direct.wav"
                    temp_files.append(temp_direct_wav)
                    
                    with open(temp_direct_wav, "wb") as f:
                        f.write(audio_data)
                    
                    # Prüfe ob es eine gültige WAV-Datei ist
                    import wave
                    with wave.open(temp_direct_wav, 'rb') as wav_file:
                        # Wenn wir bis hier kommen, ist es eine gültige WAV-Datei
                        print(f"Direct WAV interpretation successful: {temp_direct_wav}")
                        return temp_direct_wav
                        
                except Exception as wav_error:
                    print(f"Direct WAV interpretation failed: {wav_error}")
                    
                    # 5. Letzter Fallback: Erstelle stille WAV-Datei
                    print("Creating silent WAV as last resort...")
                    temp_silent = f"/tmp/live_{connection_id}_{timestamp}_silent.wav"
                    temp_files.append(temp_silent)
                    
                    # Erstelle 3 Sekunden Stille
                    import wave
                    with wave.open(temp_silent, 'wb') as wav_file:
                        wav_file.setnchannels(1)  # Mono
                        wav_file.setsampwidth(2)  # 16-bit
                        wav_file.setframerate(16000)  # 16kHz
                        
                        # 3 Sekunden Stille (16000 * 3 * 2 bytes)
                        silence = b'\x00' * (16000 * 3 * 2)
                        wav_file.writeframes(silence)
                    
                    return temp_silent
        
    except Exception as e:
        print(f"Critical error in audio processing: {e}")
        # Gebe None zurück wenn alles fehlschlägt
        return None
    finally:
        # Cleanup wird vom Aufrufer gemacht
        pass

# Dictionary für aktive Vosk-Streaming-Verbindungen
active_vosk_streams: dict[str, any] = {}
active_webm_buffers: dict[str, list] = {}  # Buffer für WebM-Chunks pro Connection
webm_stream_state: dict[str, dict] = {}  # State für kontinuierliche WebM-Streams
webm_headers: dict[str, bytes] = {}  # Gespeicherte WebM-Header pro Connection

@app.websocket("/api/transcribe-vosk-stream")
async def transcribe_vosk_stream(websocket: WebSocket):
    """
    WebSocket endpoint für kontinuierliche Vosk-basierte Spracherkennung.
    Optimiert für Echtzeit-Streaming mit minimaler Latenz.
    """
    await websocket.accept()
    connection_id = str(uuid.uuid4())
    print(f"Vosk WebSocket connected: {connection_id}")
    
    stream_transcriber = None
    result_task = None
    
    try:
        # Initialisiere Vosk Stream Transcriber
        stream_transcriber = get_vosk_stream_transcriber()
        active_vosk_streams[connection_id] = stream_transcriber
        active_webm_buffers[connection_id] = []  # Buffer für WebM-Chunks
        webm_stream_state[connection_id] = {
            'header_received': False,
            'full_stream': b'',
            'last_process_time': time.time()
        }
        
        # Starte Streaming ohne Callback - wir holen die Ergebnisse in separater Task
        stream_transcriber.start_streaming()
        
        # Task für das Abholen von Ergebnissen aus der Queue
        async def result_worker():
            print("Result worker started")
            while True:
                try:
                    if not stream_transcriber or not stream_transcriber.is_running:
                        print("Stream transcriber not running, stopping result worker")
                        break
                        
                    result = stream_transcriber.get_result(timeout=0.1)
                    if result:
                        print(f"Sending Vosk result to frontend: {result}")
                        try:
                            await websocket.send_text(json.dumps({
                                "type": "transcription",
                                "text": result['text'],
                                "partial": result['partial'],
                                "confidence": result['confidence'],
                                "timestamp": result['timestamp']
                            }))
                            print(f"Successfully sent result: {result['text'][:50]}...")
                        except Exception as send_error:
                            print(f"Error sending to websocket: {send_error}")
                            break
                except Exception as e:
                    print(f"Error in result worker: {e}")
                await asyncio.sleep(0.01)  # Kurze Pause
            print("Result worker ended")
        
        # Starte Result Worker Task
        result_task = asyncio.create_task(result_worker())
        
        chunk_counter = 0
        
        while True:
            # Empfange Nachricht vom Frontend
            message = await websocket.receive_text()
            data = json.loads(message)
            
            if data["type"] == "audio_chunk":
                chunk_counter += 1
                # Dekodiere Base64-Audio
                audio_data = base64.b64decode(data["audio"])
                print(f"Processing Vosk audio chunk {chunk_counter}: {len(audio_data)} bytes")
                
                # Debug-Analyse der Audio-Daten
                analysis = analyze_audio_data(audio_data, connection_id)
                
                # Speichere WebM-Header vom ersten vollständigen Chunk
                if analysis['is_webm'] and connection_id not in webm_headers:
                    webm_headers[connection_id] = extract_webm_header(audio_data)
                    print(f"Extracted and stored WebM header: {len(webm_headers[connection_id])} bytes")
                
                # Bessere WebM-Stream-Verarbeitung mit Header-Wiederverwendung
                stream_state = webm_stream_state[connection_id]
                current_time = time.time()
                
                # Prüfe ob es ein vollständiger WebM-Header ist
                if audio_data.startswith(b'\x1a\x45\xdf\xa3'):
                    # Neuer WebM-Stream startet
                    print(f"New WebM stream detected, resetting buffer")
                    stream_state['header_received'] = True
                    stream_state['full_stream'] = audio_data
                    stream_state['last_process_time'] = current_time
                else:
                    # Fragmentierter WebM-Chunk
                    if stream_state['header_received']:
                        stream_state['full_stream'] += audio_data
                        stream_state['last_process_time'] = current_time
                    else:
                        print(f"Fragmentary chunk received without header, skipping")
                        continue
                
                # Verarbeite Stream wenn genug Zeit vergangen oder Stream groß genug ist
                time_since_last = current_time - stream_state['last_process_time']
                stream_size = len(stream_state['full_stream'])
                
                if (stream_size > 16384 or time_since_last > 1.0 or chunk_counter % 8 == 0) and stream_size > 0:
                    print(f"Processing WebM stream: {stream_size} bytes (time_delta: {time_since_last:.2f}s)")
                    
                    # Konvertiere den kontinuierlichen WebM-Stream
                    try:
                        # Verwende die neue kontinuierliche Stream-Konvertierung
                        pcm_data = convert_continuous_webm_to_pcm(stream_state['full_stream'], connection_id)
                        if pcm_data and stream_transcriber:
                            print(f"Successfully converted {stream_size} bytes WebM stream to {len(pcm_data)} bytes PCM")
                            stream_transcriber.add_audio_chunk(pcm_data)
                            
                            # Reset Stream für nächste Batch (aber behalte letzten Teil für Kontinuität)
                            if stream_size > 32768:  # Nur bei großen Streams resetten
                                # Behalte letzten Teil des Streams für Kontinuität
                                keep_size = min(8192, stream_size // 4)
                                stream_state['full_stream'] = stream_state['full_stream'][-keep_size:]
                                print(f"Stream reset, keeping last {keep_size} bytes for continuity")
                        else:
                            print(f"Failed to convert WebM stream of {stream_size} bytes")
                            # Bei Fehlern: Versuche mit gespeichertem Header zu rekonstruieren
                            if connection_id in webm_headers and webm_headers[connection_id]:
                                print("Attempting stream reconstruction with saved header...")
                                # Teile Stream in Chunks und verwende Header-Rekonstruktion
                                chunk_size = 16384
                                stream_data = stream_state['full_stream']
                                for i in range(0, len(stream_data), chunk_size):
                                    chunk = stream_data[i:i+chunk_size]
                                    reconstructed = build_continuous_webm_stream([chunk], webm_headers[connection_id], connection_id)
                                    if reconstructed:
                                        pcm_chunk = convert_continuous_webm_to_pcm(reconstructed, connection_id)
                                        if pcm_chunk and stream_transcriber:
                                            stream_transcriber.add_audio_chunk(pcm_chunk)
                                            print(f"Successfully processed reconstructed chunk: {len(pcm_chunk)} bytes PCM")
                        
                    except Exception as e:
                        print(f"Vosk stream processing error: {e}")
                        # Reset bei Fehler
                        stream_state['full_stream'] = b''
                        stream_state['header_received'] = False
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": f"Vosk Audio-Stream-Fehler: {str(e)}"
                        }))
            
            elif data["type"] == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                
            elif data["type"] == "stop_stream":
                break
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"Vosk WebSocket Fehler: {e}")
    finally:
        # Cleanup
        if result_task:
            result_task.cancel()
            try:
                await result_task
            except asyncio.CancelledError:
                pass
        
        if connection_id in active_vosk_streams:
            if stream_transcriber:
                stream_transcriber.stop_streaming()
            del active_vosk_streams[connection_id]
            
        if connection_id in active_webm_buffers:
            del active_webm_buffers[connection_id]
            
        if connection_id in webm_stream_state:
            del webm_stream_state[connection_id]
            
        if connection_id in webm_headers:
            del webm_headers[connection_id]
            
        print(f"Vosk WebSocket disconnected: {connection_id}")

# Debug-Funktion für Audio-Analyse
def analyze_audio_data(audio_data: bytes, connection_id: str) -> Dict[str, Any]:
    """Analysiere die eingehenden Audio-Daten für Debugging."""
    analysis = {
        'size': len(audio_data),
        'first_bytes': audio_data[:20].hex() if len(audio_data) >= 20 else audio_data.hex(),
        'is_webm': False,
        'is_wav': False,
        'is_pcm': False
    }
    
    # Prüfe auf WebM/Matroska-Header
    if audio_data.startswith(b'\x1a\x45\xdf\xa3'):
        analysis['is_webm'] = True
    
    # Prüfe auf WAV-Header  
    if audio_data.startswith(b'RIFF') and b'WAVE' in audio_data[:12]:
        analysis['is_wav'] = True
    
    # Prüfe auf mögliche PCM-Daten (heuristisch)
    if len(audio_data) > 100 and not analysis['is_webm'] and not analysis['is_wav']:
        # PCM-Daten haben meist kleinere Werte
        sample_bytes = audio_data[:100]
        max_val = max(sample_bytes) if sample_bytes else 0
        if max_val < 200:  # Heuristik für PCM
            analysis['is_pcm'] = True
    
    print(f"Audio analysis for {connection_id}: {analysis}")
    return analysis

def convert_webm_to_pcm(audio_data: bytes, connection_id: str) -> bytes:
    """
    Konvertiert WebM/Opus Audio zu 16-bit PCM für Vosk.
    Optimiert für niedrige Latenz mit verbesserter Fehlerbehandlung.
    """
    import subprocess
    import tempfile
    
    timestamp = uuid.uuid4().hex[:8]
    
    # Prüfe Datengrößse - sehr kleine Chunks sind oft unvollständig
    if len(audio_data) < 100:
        print(f"Audio chunk too small ({len(audio_data)} bytes), skipping")
        return b""
    
    # Temporäre Dateien
    temp_webm = f"/tmp/vosk_{connection_id}_{timestamp}.webm"
    temp_wav = f"/tmp/vosk_{connection_id}_{timestamp}.wav"
    temp_raw = f"/tmp/vosk_{connection_id}_{timestamp}.raw"
    
    try:
        # Schreibe WebM-Daten
        with open(temp_webm, "wb") as f:
            f.write(audio_data)
        
        print(f"Processing {len(audio_data)} bytes audio chunk")
        
        # Methode 1: WebM zu WAV mit ffmpeg (robusteste Methode)
        try:
            cmd = [
                'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
                '-i', temp_webm,
                '-ar', '16000',  # 16kHz Sample Rate für Vosk
                '-ac', '1',      # Mono
                '-f', 'wav',     # WAV Format
                '-acodec', 'pcm_s16le',  # 16-bit PCM
                temp_wav
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and os.path.exists(temp_wav) and os.path.getsize(temp_wav) > 44:
                # Lese WAV-Datei und extrahiere PCM-Daten
                with wave.open(temp_wav, 'rb') as wav_file:
                    # Validiere WAV-Format
                    sample_rate = wav_file.getframerate()
                    channels = wav_file.getnchannels()
                    sample_width = wav_file.getsampwidth()
                    
                    print(f"WAV file: {sample_rate}Hz, {channels} channels, {sample_width} bytes/sample")
                    
                    if sample_rate != 16000:
                        print(f"Warning: Sample rate is {sample_rate}, expected 16000")
                    if channels != 1:
                        print(f"Warning: {channels} channels, expected 1 (mono)")
                    if sample_width != 2:
                        print(f"Warning: {sample_width} bytes/sample, expected 2 (16-bit)")
                    
                    pcm_data = wav_file.readframes(wav_file.getnframes())
                    print(f"Successfully converted to {len(pcm_data)} bytes PCM")
                    return pcm_data
            else:
                print(f"FFmpeg conversion failed: {result.stderr}")
                    
        except subprocess.TimeoutExpired:
            print("FFmpeg timeout")
        except Exception as e:
            print(f"FFmpeg conversion failed: {e}")
        
        # Methode 2: Direct WebM to RAW PCM
        try:
            cmd = [
                'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
                '-i', temp_webm,
                '-ar', '16000',
                '-ac', '1',
                '-f', 's16le',  # 16-bit little-endian PCM
                temp_raw
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and os.path.exists(temp_raw) and os.path.getsize(temp_raw) > 0:
                with open(temp_raw, 'rb') as f:
                    pcm_data = f.read()
                    if len(pcm_data) > 0:
                        print(f"RAW PCM conversion successful: {len(pcm_data)} bytes")
                        return pcm_data
            else:
                print(f"RAW PCM conversion failed: {result.stderr}")
                        
        except Exception as e:
            print(f"RAW PCM conversion failed: {e}")
        
        # Methode 3: Versuche verschiedene Input-Formate
        for input_format in ['webm', 'ogg', 'opus']:
            try:
                cmd = [
                    'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
                    '-f', input_format, '-i', temp_webm,
                    '-ar', '16000', '-ac', '1', '-f', 's16le',
                    temp_raw
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                
                if result.returncode == 0 and os.path.exists(temp_raw) and os.path.getsize(temp_raw) > 0:
                    with open(temp_raw, 'rb') as f:
                        pcm_data = f.read()
                        if len(pcm_data) > 0:
                            print(f"Format {input_format} conversion successful: {len(pcm_data)} bytes PCM")
                            return pcm_data
                            
            except Exception as e:
                continue
        
        print(f"All conversion methods failed for {len(audio_data)} bytes")
        return b""
            
    except Exception as e:
        print(f"Critical audio conversion error: {e}")
        return b""
    finally:
        # Cleanup temporäre Dateien
        for temp_file in [temp_webm, temp_wav, temp_raw]:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass

def convert_webm_to_pcm_buffered(audio_data: bytes, connection_id: str) -> bytes:
    """
    Konvertiert gesammelte WebM/Opus Audio-Chunks zu 16-bit PCM für Vosk.
    Optimiert für WebM-Streaming mit fragmentierten Chunks.
    """
    import subprocess
    import tempfile
    
    timestamp = uuid.uuid4().hex[:8]
    
    # Prüfe Datengrößse
    if len(audio_data) < 200:
        print(f"Combined audio chunk too small ({len(audio_data)} bytes), skipping")
        return b""
    
    # Temporäre Dateien
    temp_webm = f"/tmp/vosk_combined_{connection_id}_{timestamp}.webm"
    temp_wav = f"/tmp/vosk_combined_{connection_id}_{timestamp}.wav"
    temp_raw = f"/tmp/vosk_combined_{connection_id}_{timestamp}.raw"
    
    try:
        # Schreibe kombinierte WebM-Daten
        with open(temp_webm, "wb") as f:
            f.write(audio_data)
        
        print(f"Processing combined audio chunk: {len(audio_data)} bytes")
        
        # Methode 1: WebM zu WAV mit ffmpeg (robusteste Methode für kombinierte Daten)
        try:
            cmd = [
                'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
                '-fflags', '+genpts',  # Generate PTS für fragmentierte Streams
                '-i', temp_webm,
                '-ar', '16000',  # 16kHz Sample Rate für Vosk
                '-ac', '1',      # Mono
                '-f', 'wav',     # WAV Format
                '-acodec', 'pcm_s16le',  # 16-bit PCM
                temp_wav
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0 and os.path.exists(temp_wav) and os.path.getsize(temp_wav) > 44:
                # Lese WAV-Datei und extrahiere PCM-Daten
                with wave.open(temp_wav, 'rb') as wav_file:
                    # Validiere WAV-Format
                    sample_rate = wav_file.getframerate()
                    channels = wav_file.getnchannels()
                    sample_width = wav_file.getsampwidth()
                    
                    print(f"Combined WAV: {sample_rate}Hz, {channels} channels, {sample_width} bytes/sample")
                    
                    pcm_data = wav_file.readframes(wav_file.getnframes())
                    print(f"Successfully converted combined chunk to {len(pcm_data)} bytes PCM")
                    return pcm_data
            else:
                print(f"Combined FFmpeg conversion failed: {result.stderr}")
                    
        except subprocess.TimeoutExpired:
            print("Combined FFmpeg timeout")
        except Exception as e:
            print(f"Combined FFmpeg conversion failed: {e}")
        
        # Methode 2: Direct WebM to RAW PCM (für fragmentierte Streams)
        try:
            cmd = [
                'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
                '-fflags', '+genpts',  # Generate PTS
                '-analyzeduration', '1000000',  # Analysiere länger für fragmentierte Streams
                '-probesize', '1000000',
                '-i', temp_webm,
                '-ar', '16000',
                '-ac', '1',
                '-f', 's16le',  # 16-bit little-endian PCM
                temp_raw
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0 and os.path.exists(temp_raw) and os.path.getsize(temp_raw) > 0:
                with open(temp_raw, 'rb') as f:
                    pcm_data = f.read()
                    if len(pcm_data) > 0:
                        print(f"Combined RAW PCM conversion successful: {len(pcm_data)} bytes")
                        return pcm_data
            else:
                print(f"Combined RAW PCM conversion failed: {result.stderr}")
                        
        except Exception as e:
            print(f"Combined RAW PCM conversion failed: {e}")
        
        # Methode 3: Versuche als concatenated WebM stream
        try:
            cmd = [
                'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
                '-f', 'matroska', '-i', temp_webm,  # Explizit Matroska/WebM format
                '-ar', '16000', '-ac', '1', '-f', 's16le',
                temp_raw
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and os.path.exists(temp_raw) and os.path.getsize(temp_raw) > 0:
                with open(temp_raw, 'rb') as f:
                    pcm_data = f.read()
                    if len(pcm_data) > 0:
                        print(f"Matroska format conversion successful: {len(pcm_data)} bytes PCM")
                        return pcm_data
                        
        except Exception as e:
            print(f"Matroska conversion failed: {e}")
        
        print(f"All combined conversion methods failed for {len(audio_data)} bytes")
        return b""
            
    except Exception as e:
        print(f"Critical combined audio conversion error: {e}")
        return b""
    finally:
        # Cleanup temporäre Dateien
        for temp_file in [temp_webm, temp_wav, temp_raw]:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass

def extract_webm_header(webm_data: bytes) -> bytes:
    """
    Extrahiert den WebM-Header aus vollständigen WebM-Daten.
    Der Header wird für die Rekonstruktion fragmentierter Streams benötigt.
    """
    try:
        if not webm_data.startswith(b'\x1a\x45\xdf\xa3'):
            return b''
        
        # WebM/Matroska Header-Parsing (vereinfacht)
        # Suche nach dem ersten Cluster-Element (Audio-Daten)
        cluster_marker = b'\x1f\x43\xb6\x75'  # Cluster EBML ID
        
        cluster_pos = webm_data.find(cluster_marker)
        if cluster_pos > 0:
            # Header ist alles vor dem ersten Cluster
            header = webm_data[:cluster_pos]
            print(f"WebM header extracted: {len(header)} bytes (cluster at {cluster_pos})")
            return header
        else:
            # Fallback: Nehme ersten Teil als Header (bis zu 8KB)
            header_size = min(8192, len(webm_data) // 2)
            header = webm_data[:header_size]
            print(f"WebM header fallback: {len(header)} bytes")
            return header
            
    except Exception as e:
        print(f"Error extracting WebM header: {e}")
        return b''

def build_continuous_webm_stream(chunks: list, header: bytes, connection_id: str) -> bytes:
    """
    Baut einen kontinuierlichen WebM-Stream aus fragmentierten Chunks auf.
    Verwendet den gespeicherten Header für fragmentierte Chunks ohne Header.
    """
    try:
        if not chunks:
            return b''
        
        # Prüfe ob der erste Chunk bereits einen Header hat
        first_chunk = chunks[0]
        if first_chunk.startswith(b'\x1a\x45\xdf\xa3'):
            # Vollständiger WebM-Stream, kombiniere alle Chunks
            return b''.join(chunks)
        
        # Fragmentierte Chunks - verwende gespeicherten Header
        if not header:
            print(f"No header available for connection {connection_id}")
            return b''
        
        # Baue Stream mit Header + fragmentierte Audio-Daten
        audio_data = b''.join(chunks)
        continuous_stream = header + audio_data
        
        print(f"Built continuous WebM stream: {len(header)} bytes header + {len(audio_data)} bytes data = {len(continuous_stream)} bytes total")
        return continuous_stream
        
    except Exception as e:
        print(f"Error building continuous WebM stream: {e}")
        return b''

def convert_continuous_webm_to_pcm(webm_data: bytes, connection_id: str) -> bytes:
    """
    Konvertiert einen kontinuierlichen WebM-Stream zu 16-bit PCM für Vosk.
    Optimiert für rekonstruierte WebM-Streams aus fragmentierten Chunks.
    """
    import subprocess
    import tempfile
    
    timestamp = uuid.uuid4().hex[:8]
    
    if len(webm_data) < 500:
        print(f"WebM stream too small ({len(webm_data)} bytes), skipping")
        return b""
    
    # Temporäre Dateien
    temp_webm = f"/tmp/vosk_continuous_{connection_id}_{timestamp}.webm"
    temp_wav = f"/tmp/vosk_continuous_{connection_id}_{timestamp}.wav"
    temp_raw = f"/tmp/vosk_continuous_{connection_id}_{timestamp}.raw"
    
    try:
        # Schreibe kontinuierlichen WebM-Stream
        with open(temp_webm, "wb") as f:
            f.write(webm_data)
        
        print(f"Processing continuous WebM stream: {len(webm_data)} bytes")
        
        # Methode 1: WebM zu WAV mit erweiterten Parametern für rekonstruierte Streams
        try:
            cmd = [
                'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
                '-fflags', '+genpts+igndts',  # Generate PTS + ignore DTS für rekonstruierte Streams
                '-analyzeduration', '2000000',  # Längere Analyse für fragmentierte Streams
                '-probesize', '2000000',
                '-err_detect', 'ignore_err',  # Ignoriere kleinere Fehler in rekonstruierten Streams
                '-i', temp_webm,
                '-ar', '16000',  # 16kHz Sample Rate für Vosk
                '-ac', '1',      # Mono
                '-f', 'wav',     # WAV Format
                '-acodec', 'pcm_s16le',  # 16-bit PCM
                temp_wav
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            
            if result.returncode == 0 and os.path.exists(temp_wav) and os.path.getsize(temp_wav) > 44:
                # Lese WAV-Datei und extrahiere PCM-Daten
                with wave.open(temp_wav, 'rb') as wav_file:
                    sample_rate = wav_file.getframerate()
                    channels = wav_file.getnchannels()
                    sample_width = wav_file.getsampwidth()
                    
                    print(f"Continuous WAV: {sample_rate}Hz, {channels} channels, {sample_width} bytes/sample")
                    
                    pcm_data = wav_file.readframes(wav_file.getnframes())
                    print(f"Successfully converted continuous stream to {len(pcm_data)} bytes PCM")
                    return pcm_data
            else:
                print(f"Continuous FFmpeg conversion failed: {result.stderr}")
                    
        except subprocess.TimeoutExpired:
            print("Continuous FFmpeg timeout")
        except Exception as e:
            print(f"Continuous FFmpeg conversion failed: {e}")
        
        # Methode 2: Direct WebM to RAW PCM mit Fehlertoleranz
        try:
            cmd = [
                'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
                '-fflags', '+genpts+igndts',
                '-analyzeduration', '2000000',
                '-probesize', '2000000',
                '-err_detect', 'ignore_err',
                '-i', temp_webm,
                '-ar', '16000',
                '-ac', '1',
                '-f', 's16le',  # 16-bit little-endian PCM
                temp_raw
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            
            if result.returncode == 0 and os.path.exists(temp_raw) and os.path.getsize(temp_raw) > 0:
                with open(temp_raw, 'rb') as f:
                    pcm_data = f.read()
                    if len(pcm_data) > 0:
                        print(f"Continuous RAW PCM conversion successful: {len(pcm_data)} bytes")
                        return pcm_data
            else:
                print(f"Continuous RAW PCM conversion failed: {result.stderr}")
                        
        except Exception as e:
            print(f"Continuous RAW PCM conversion failed: {e}")
        
        print(f"All continuous conversion methods failed for {len(webm_data)} bytes")
        return b""
            
    except Exception as e:
        print(f"Critical continuous audio conversion error: {e}")
        return b""
    finally:
        # Cleanup temporäre Dateien
        for temp_file in [temp_webm, temp_wav, temp_raw]:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
