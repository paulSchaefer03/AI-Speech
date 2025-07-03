# Vosk Live-Streaming Integration - Dokumentation

## Übersicht

Die Vosk-Integration wurde erfolgreich in das Backend und Frontend implementiert und bietet echte Live-Streaming-Transkription für deutsche Sprache mit niedrigster Latenz.

## Implementierte Features

### Backend-Erweiterungen

1. **Lazy Loading System**
   - Modelle werden nur bei Bedarf geladen (Performance-Optimierung)
   - Modell-Status-Tracking über `/api/model-status/{model_name}`
   - Vorladen von Modellen über `/api/preload-model`

2. **Vosk-Transkription Module (`backend/vosk_transcription.py`)**
   - `VoskTranscriber`: Einzeldatei-Transkription
   - `VoskStreamTranscriber`: Kontinuierliche Streaming-Transkription
   - Lazy Loading für bessere Performance
   - Unterstützung für Word-Level Timestamps und Confidence Scores

3. **WebSocket Endpoints**
   - `/api/transcribe-live`: Standard Live-Transkription 
   - `/api/transcribe-vosk-stream`: Optimierte Vosk-Live-Streaming-Transkription
   - Audio-Format-Konvertierung (WebM/Opus → PCM 16kHz Mono)

4. **Audio-Processing**
   - Robuste WebM-zu-PCM-Konvertierung mit ffmpeg
   - Optimiert für niedrige Latenz
   - Automatische Cleanup von temporären Dateien

### Frontend-Erweiterungen

1. **VoskLiveTranscription Component (`frontend/src/components/AI-Speech/VoskLiveTranscription.tsx`)**
   - Live-Streaming-Interface für Vosk
   - Modell-Ladestatus mit visueller Anzeige
   - Kontinuierliche Audioaufnahme mit 100ms Chunks
   - Partial und finale Transkriptionsergebnisse
   - Automatisches Cleanup beim Beenden

2. **API-Erweiterungen (`frontend/src/components/API/transcription.ts`)**
   - `VoskLiveTranscription` WebSocket-Klasse für Streaming
   - `getModelStatus()` und `preloadModel()` Funktionen
   - Optimierte Audio-Chunk-Übertragung

3. **UI-Integration (`frontend/src/pages/HomePage.tsx`)**
   - Separater Bereich für Vosk Live-Streaming
   - Übersichtliche Trennung von Standard- und Live-Transkription

## Verwendung

### 1. Backend starten
```bash
cd /home/paul-schaefer/Dokumente/Klinikum_Fulda/Spech_to_Text_Demo
./asr_env/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 7860
```

### 2. Frontend verwenden
1. Öffnen Sie die Anwendung im Browser
2. Im Bereich "Vosk Live-Transkription":
   - Klicken Sie auf "Vosk-Modell laden" (einmalig)
   - Warten Sie auf die Ladeanzeige
   - Klicken Sie auf "Live-Streaming starten"
   - Sprechen Sie ins Mikrofon
   - Sehen Sie Echtzeit-Transkription (partial + final)

### 3. API-Endpoints testen
```bash
# Modell-Status prüfen
curl http://localhost:7860/api/model-status/Vosk%20German

# Modell vorladen
curl -X POST http://localhost:7860/api/preload-model \
  -H "Content-Type: application/json" \
  -d '{"model_name": "Vosk German"}'

# Verfügbare Modelle anzeigen
curl http://localhost:7860/api/models
```

## Technische Details

### Audio-Pipeline
1. **Frontend**: MediaRecorder (WebM/Opus, 100ms Chunks)
2. **Übertragung**: Base64-kodierte WebSocket-Messages
3. **Backend**: ffmpeg-Konvertierung zu 16kHz Mono PCM
4. **Vosk**: Direkte PCM-Verarbeitung für minimale Latenz

### Performance-Optimierungen
- **Lazy Loading**: Modelle werden erst bei Gebrauch geladen
- **Chunked Processing**: 100ms Audio-Chunks für responsive Transkription  
- **Direct PCM**: Keine unnötigen Audio-Konvertierungen in Vosk
- **Asynchrone Verarbeitung**: WebSocket-Handler blockieren nicht

### Modell-Spezifikationen
- **Modell**: vosk-model-de-tuda-0.6-900k
- **Sprache**: Deutsch
- **Sample Rate**: 16kHz
- **Kanäle**: Mono
- **Format**: 16-bit PCM

## Fehlerbehebung

### Häufige Probleme

1. **Modell nicht gefunden**
   - Prüfen Sie, ob `/vosk-model-de-tuda-0.6-900k/` existiert
   - Extrahieren Sie das Modell falls nötig: `unzip vosk-model-de.zip`

2. **Audio-Konvertierung fehlgeschlagen**
   - Stellen Sie sicher, dass ffmpeg installiert ist: `which ffmpeg`
   - Prüfen Sie Mikrofon-Berechtigungen im Browser

3. **WebSocket-Verbindung fehlgeschlagen**
   - Prüfen Sie Backend-Status: `curl http://localhost:7860/api/models`
   - Überprüfen Sie CORS-Einstellungen

4. **Schlechte Transkriptionsqualität**
   - Verwenden Sie ein gutes Mikrofon
   - Sprechen Sie deutlich und nicht zu schnell
   - Reduzieren Sie Hintergrundgeräusche

## Nächste Schritte

### Mögliche Erweiterungen
1. **Voice Activity Detection (VAD)**: Nur sprechen wenn erkannt
2. **Adaptive Chunk-Größe**: Dynamische Anpassung basierend auf Netzwerk
3. **Multiple Modelle**: Parallel-Verarbeitung verschiedener Modelle
4. **Noise Reduction**: Integrierte Geräuschunterdrückung
5. **Speaker Diarization**: Sprechererkennung für mehrere Personen

### Performance-Verbesserungen
1. **GPU-Acceleration**: CUDA-Support für Vosk falls verfügbar
2. **Model Quantization**: Kleinere, schnellere Modelle
3. **Edge Computing**: Client-seitige Verarbeitung für niedrigste Latenz

## Status

✅ **Erfolgreich implementiert:**
- Vosk-Backend-Integration
- Live-Streaming WebSocket
- Frontend-Komponente
- Lazy Loading System
- Audio-Format-Konvertierung
- Model-Status-Tracking

🔄 **Getestet und funktionsfähig:**
- Einzeldatei-Transkription mit Vosk
- WebSocket-Verbindungen
- Model Loading/Unloading
- Audio-Chunk-Verarbeitung

Die Vosk-Integration ist vollständig und einsatzbereit für Live-Streaming-Transkription!
