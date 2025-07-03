#!/usr/bin/env python3

import sys
import os
sys.path.append('/home/paul-schaefer/Dokumente/Klinikum_Fulda/Spech_to_Text_Demo')

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Test importing the backend
try:
    from backend.main import app
    print("✓ Backend imported successfully")
    
    # Create test client
    client = TestClient(app)
    
    # Test the models endpoint
    response = client.get("/api/models")
    print(f"✓ Models endpoint response: {response.status_code}")
    
    if response.status_code == 200:
        models = response.json()
        print(f"✓ Available models: {models['models']}")
        
        if "Vosk German" in models['models']:
            print("✓ Vosk German model is available in the API")
        else:
            print("✗ Vosk German model not found in the API")
    
    print("\nBackend integration test completed successfully!")
    
except Exception as e:
    import traceback
    print(f"✗ Error: {e}")
    traceback.print_exc()
