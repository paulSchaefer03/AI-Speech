#!/usr/bin/env python3
"""
Test WebSocket mit echter WAV-Datei
"""

import asyncio
import websockets
import json
import base64
import wave
import os

async def test_websocket_with_wav():
    uri = "ws://localhost:7860/api/transcribe-vosk-stream"
    
    # Verwende die Test-Audio-Datei
    audio_file = "/home/paul-schaefer/Dokumente/Klinikum_Fulda/Spech_to_Text_Demo/testAudio/Test_Quantenphysik.wav"
    
    if not os.path.exists(audio_file):
        print(f"Audio file not found: {audio_file}")
        return
    
    # Konvertiere zu 16kHz Mono für bessere Kompatibilität
    temp_wav = "/tmp/test_16k_mono.wav"
    
    import subprocess
    try:
        cmd = [
            'ffmpeg', '-y', '-i', audio_file,
            '-ar', '16000',  # 16kHz
            '-ac', '1',      # Mono
            '-f', 'wav',
            temp_wav
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"FFmpeg conversion failed: {result.stderr}")
            return
    except Exception as e:
        print(f"Audio conversion error: {e}")
        return
    
    # Lese konvertierte WAV-Datei
    with wave.open(temp_wav, 'rb') as wav_file:
        print(f"WAV: {wav_file.getframerate()}Hz, {wav_file.getnchannels()} channels, {wav_file.getnframes()} frames")
        
        # Lese alle Audio-Daten
        audio_data = wav_file.readframes(wav_file.getnframes())
        print(f"Total audio data: {len(audio_data)} bytes")
        
        # Teile in kleinere Chunks (2 Sekunden = 32000 Samples = 64000 bytes)
        chunk_size = 64000
        chunks = [audio_data[i:i+chunk_size] for i in range(0, len(audio_data), chunk_size)]
        print(f"Created {len(chunks)} chunks")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("WebSocket connected")
            
            # Sende Audio-Chunks
            for i, chunk in enumerate(chunks):
                # Erstelle WAV-Header für den Chunk
                chunk_wav = create_wav_chunk(chunk, 16000, 1)
                
                message = {
                    "type": "audio_chunk",
                    "audio": base64.b64encode(chunk_wav).decode('utf-8')
                }
                
                await websocket.send(json.dumps(message))
                print(f"Sent chunk {i+1}/{len(chunks)}: {len(chunk_wav)} bytes")
                
                # Warte kurz zwischen Chunks
                await asyncio.sleep(0.1)
            
            print("All chunks sent, waiting for results...")
            
            # Warte auf Antworten
            results = []
            for i in range(50):  # Warte max 50 Nachrichten
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    data = json.loads(response)
                    
                    print(f"Received: {data}")
                    
                    if data.get("type") == "transcription":
                        text = data.get('text', '')
                        partial = data.get('partial', False)
                        print(f"{'[PARTIAL]' if partial else '[FINAL]'} Transcription: {text}")
                        if not partial and text:
                            results.append(text)
                            
                except asyncio.TimeoutError:
                    print(f"Timeout after {i+1} messages")
                    break
                    
            # Stoppe Stream
            await websocket.send(json.dumps({"type": "stop_stream"}))
            print("Stream stopped")
            
            # Zeige finale Ergebnisse
            if results:
                print("\n=== FINAL TRANSCRIPTION RESULTS ===")
                for i, result in enumerate(results):
                    print(f"{i+1}: {result}")
            else:
                print("\n=== NO TRANSCRIPTION RESULTS ===")
            
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        # Cleanup
        if os.path.exists(temp_wav):
            os.remove(temp_wav)

def create_wav_chunk(pcm_data, sample_rate, channels):
    """Erstelle WAV-Header für PCM-Daten"""
    import struct
    
    bits_per_sample = 16
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    data_size = len(pcm_data)
    
    header = struct.pack('<4sI4s4sIHHIIHH4sI',
        b'RIFF',
        36 + data_size,
        b'WAVE',
        b'fmt ',
        16,  # PCM
        1,   # PCM format
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b'data',
        data_size
    )
    
    return header + pcm_data

if __name__ == "__main__":
    asyncio.run(test_websocket_with_wav())
