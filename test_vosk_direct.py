#!/usr/bin/env python3
"""
Einfacher Test für Vosk-Transkription ohne WebSocket
"""

import sys
import os

# Pfad hinzufügen
sys.path.append('/home/paul-schaefer/Dokumente/Klinikum_Fulda/Spech_to_Text_Demo')

from backend.vosk_transcription import get_vosk_stream_transcriber
import wave
import numpy as np
import time
import threading

def test_vosk_directly():
    print("=== Vosk Direct Test ===")
    
    # Erstelle Test-Audio
    sample_rate = 16000
    duration = 2.0
    frequency = 440  # A4
    
    # Generiere Sinuston
    t = np.linspace(0, duration, int(sample_rate * duration))
    audio_data = np.sin(2 * np.pi * frequency * t)
    
    # Konvertiere zu 16-bit PCM
    audio_data = (audio_data * 32767).astype(np.int16)
    
    print(f"Generated test audio: {len(audio_data)} samples")
    
    # Teste Vosk Stream Transcriber
    transcriber = get_vosk_stream_transcriber()
    
    def result_callback(result):
        print(f"Callback result: {result}")
    
    print("Starting Vosk streaming...")
    transcriber.start_streaming(result_callback)
    
    # Sende Audio in Chunks
    chunk_size = 8000  # 0.5 Sekunden
    for i in range(0, len(audio_data), chunk_size):
        chunk = audio_data[i:i+chunk_size]
        chunk_bytes = chunk.tobytes()
        
        print(f"Sending chunk {i//chunk_size + 1}: {len(chunk_bytes)} bytes")
        transcriber.add_audio_chunk(chunk_bytes)
        
        time.sleep(0.1)  # Kurze Pause
    
    # Warte auf Ergebnisse
    print("Waiting for results...")
    for i in range(50):  # 5 Sekunden warten
        result = transcriber.get_result(timeout=0.1)
        if result:
            print(f"Direct result: {result}")
        time.sleep(0.1)
    
    print("Stopping transcriber...")
    transcriber.stop_streaming()
    print("Test completed.")

if __name__ == "__main__":
    test_vosk_directly()
