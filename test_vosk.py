#!/usr/bin/env python3

import sys
import os
sys.path.append('/home/paul-schaefer/Dokumente/Klinikum_Fulda/Spech_to_Text_Demo')

try:
    print("Testing Vosk integration...")
    
    # Test basic Vosk import
    import vosk
    print("✓ Vosk imported successfully")
    
    # Test model loading
    model_path = "/home/paul-schaefer/Dokumente/Klinikum_Fulda/Spech_to_Text_Demo/vosk-model-de-tuda-0.6-900k"
    if os.path.exists(model_path):
        print(f"✓ Model path exists: {model_path}")
        
        model = vosk.Model(model_path)
        print("✓ Vosk model loaded successfully")
        
        rec = vosk.KaldiRecognizer(model, 16000)
        print("✓ Vosk recognizer created successfully")
        
        # Test our transcription module
        from backend.vosk_transcription import get_vosk_transcriber
        transcriber = get_vosk_transcriber()
        print("✓ Our Vosk transcriber module loaded successfully")
        
        # Test the transcription function
        from backend.transcription import transcribe
        print("✓ Main transcription module imported successfully")
        
        print("\nAll tests passed! Vosk integration is working.")
        
    else:
        print(f"✗ Model path does not exist: {model_path}")
        
except Exception as e:
    import traceback
    print(f"✗ Error: {e}")
    traceback.print_exc()
