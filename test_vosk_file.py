#!/usr/bin/env python3
"""
Test Vosk mit echter WAV-Datei
"""

import sys
import os

# Pfad hinzufügen
sys.path.append('/home/paul-schaefer/Dokumente/Klinikum_Fulda/Spech_to_Text_Demo')

from backend.vosk_transcription import get_vosk_transcriber

def test_vosk_with_file():
    print("=== Vosk File Test ===")
    
    # Teste mit der vorhandenen Audio-Datei
    audio_file = "/home/paul-schaefer/Dokumente/Klinikum_Fulda/Spech_to_Text_Demo/testAudio/Test_Quantenphysik.wav"
    
    if not os.path.exists(audio_file):
        print(f"Audio file not found: {audio_file}")
        return
    
    print(f"Testing with file: {audio_file}")
    
    transcriber = get_vosk_transcriber()
    result = transcriber.transcribe_file(audio_file)
    
    print(f"Transcription result: {result}")

if __name__ == "__main__":
    test_vosk_with_file()
