#!/usr/bin/env python3
"""
Test-Skript für Vosk WebSocket Debugging
"""

import asyncio
import websockets
import json
import base64
import wave
import numpy as np

async def test_vosk_websocket():
    uri = "ws://localhost:7860/api/transcribe-vosk-stream"
    
    # Erstelle Test-Audio (1 Sekunde Sinuston bei 16kHz)
    sample_rate = 16000
    duration = 1.0
    frequency = 440  # A4
    
    # Generiere Sinuston
    t = np.linspace(0, duration, int(sample_rate * duration))
    audio_data = np.sin(2 * np.pi * frequency * t)
    
    # Konvertiere zu 16-bit PCM
    audio_data = (audio_data * 32767).astype(np.int16)
    
    # Erstelle WAV-Datei im Speicher
    import io
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_data.tobytes())
    
    wav_data = wav_buffer.getvalue()
    print(f"Generated test audio: {len(wav_data)} bytes")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("WebSocket connected")
            
            # Sende Audio-Chunk
            message = {
                "type": "audio_chunk",
                "audio": base64.b64encode(wav_data).decode('utf-8')
            }
            
            await websocket.send(json.dumps(message))
            print("Audio chunk sent")
            
            # Warte auf Antworten
            for i in range(10):  # Warte max 10 Nachrichten
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    data = json.loads(response)
                    print(f"Received: {data}")
                    
                    if data.get("type") == "transcription":
                        print(f"Transcription: {data.get('text', 'N/A')}")
                        
                except asyncio.TimeoutError:
                    print("Timeout waiting for response")
                    break
                    
            # Stoppe Stream
            await websocket.send(json.dumps({"type": "stop_stream"}))
            print("Stream stopped")
            
    except Exception as e:
        print(f"WebSocket error: {e}")

if __name__ == "__main__":
    asyncio.run(test_vosk_websocket())
