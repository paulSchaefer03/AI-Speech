#!/usr/bin/env python3
"""
Test-Script für die Vosk-Integration
"""

import sys
import os
sys.path.append('/home/paul-schaefer/Dokumente/Klinikum_Fulda/Spech_to_Text_Demo')

def test_vosk_lazy_loading():
    """Test lazy loading der Vosk-Modelle"""
    print("Testing Vosk lazy loading...")
    
    from backend.vosk_transcription import get_vosk_transcriber
    
    # Erstelle Transcriber - sollte nicht sofort das Modell laden
    print("Creating VoskTranscriber instance...")
    transcriber = get_vosk_transcriber()
    print("VoskTranscriber created successfully")
    
    # Test mit einer Dummy-Audio-Datei
    test_audio_path = "/home/paul-schaefer/Dokumente/Klinikum_Fulda/Spech_to_Text_Demo/testAudio/Test_Quantenphysik.wav"
    
    if os.path.exists(test_audio_path):
        print(f"Testing transcription with {test_audio_path}")
        try:
            result = transcriber.transcribe_file(test_audio_path)
            print(f"Transcription result: {result[:100]}...")
        except Exception as e:
            print(f"Transcription error: {e}")
    else:
        print(f"Test audio file not found: {test_audio_path}")

def test_backend_endpoints():
    """Test Backend-Endpunkte"""
    print("\nTesting backend endpoints...")
    
    try:
        from backend.main import model_status
        print("Model status:", model_status)
    except Exception as e:
        print(f"Error testing endpoints: {e}")

if __name__ == "__main__":
    test_vosk_lazy_loading()
    test_backend_endpoints()
    print("\nTest completed!")
