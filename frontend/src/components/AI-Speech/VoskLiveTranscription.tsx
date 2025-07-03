import React, { useState, useRef, useEffect } from 'react';
import { Mic, MicOff, Play, Square, Loader2 } from 'lucide-react';
import { Button } from '../ui/button';
import { VoskLiveTranscription as VoskWebSocket, preloadModel, getModelStatus } from '../API/transcription';

interface VoskLiveTranscriptionProps {
  onTranscription?: (text: string, partial: boolean, confidence: number) => void;
}

export function VoskLiveTranscription({ onTranscription }: VoskLiveTranscriptionProps) {
  const [isRecording, setIsRecording] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [modelLoading, setModelLoading] = useState(false);
  const [modelLoaded, setModelLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentText, setCurrentText] = useState('');
  const [partialText, setPartialText] = useState('');
  
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const voskWSRef = useRef<VoskWebSocket | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // Modell-Status überprüfen
  useEffect(() => {
    checkModelStatus();
  }, []);

  const checkModelStatus = async () => {
    try {
      const status = await getModelStatus('Vosk German');
      setModelLoaded(status.loaded);
      setModelLoading(status.loading);
    } catch (error) {
      console.error('Fehler beim Abrufen des Modellstatus:', error);
    }
  };

  const loadModel = async () => {
    if (modelLoaded || modelLoading) return;
    
    setModelLoading(true);
    setError(null);
    
    try {
      await preloadModel('Vosk German');
      setModelLoaded(true);
    } catch (error) {
      setError('Fehler beim Laden des Vosk-Modells');
      console.error('Model loading error:', error);
    } finally {
      setModelLoading(false);
    }
  };

  const startStreaming = async () => {
    if (!modelLoaded) {
      await loadModel();
      if (!modelLoaded) return;
    }

    try {
      setError(null);
      
      // Mikrofon-Stream anfordern mit spezifischen Einstellungen für bessere Kompatibilität
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });
      
      streamRef.current = stream;
      
      // Prüfe MediaRecorder-Unterstützung
      const supportedTypes = [
        'audio/webm; codecs=opus',
        'audio/webm',
        'audio/ogg; codecs=opus',
        'audio/mp4',
        'audio/mpeg'
      ];
      
      let selectedMimeType = 'audio/webm; codecs=opus'; // Default
      for (const type of supportedTypes) {
        if (MediaRecorder.isTypeSupported(type)) {
          selectedMimeType = type;
          console.log(`Using MIME type: ${type}`);
          break;
        }
      }
      
      // WebSocket-Verbindung zur Vosk-API
      voskWSRef.current = new VoskWebSocket(
        (text: string, partial: boolean, confidence: number) => {
          if (partial) {
            setPartialText(text);
          } else {
            setCurrentText(prev => prev + ' ' + text);
            setPartialText('');
          }
          onTranscription?.(text, partial, confidence);
        },
        (error: string) => {
          setError(error);
        },
        () => {
          setIsConnected(true);
        },
        () => {
          setIsConnected(false);
        }
      );
      
      if (voskWSRef.current) {
        await voskWSRef.current.connect();
      }
      
      // MediaRecorder für kontinuierliche Chunks mit verbessertem Chunking
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: selectedMimeType
      });
      
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];
      
      let chunkCounter = 0;
      let audioBuffer: Blob[] = [];
      
      mediaRecorder.ondataavailable = async (event) => {
        if (event.data.size > 0 && voskWSRef.current) {
          chunkCounter++;
          console.log(`Audio chunk ${chunkCounter}: ${event.data.size} bytes, type: ${event.data.type}`);
          
          // Sammle Chunks für stabilere WebM-Streams
          audioBuffer.push(event.data);
          
          // Verarbeite gesammelte Chunks für bessere WebM-Kontinuität
          const totalSize = audioBuffer.reduce((sum, chunk) => sum + chunk.size, 0);
          
          // Sende größere, stabilere Chunks seltener aber vollständiger
          if (audioBuffer.length >= 5 || totalSize > 20480 || chunkCounter % 10 === 0) {
            console.log(`Processing ${audioBuffer.length} buffered chunks, total size: ${totalSize} bytes`);
            
            try {
              // Kombiniere alle Chunks in einen großen, stabilen Blob
              const combinedBlob = new Blob(audioBuffer, { type: selectedMimeType });
              console.log(`Sending stable combined chunk: ${combinedBlob.size} bytes`);
              
              await voskWSRef.current.sendAudioChunk(combinedBlob);
              
              // Reset buffer
              audioBuffer = [];
              
            } catch (error) {
              console.error('Fehler beim Senden von stabilen Audio-Chunks:', error);
              audioBuffer = []; // Reset auch bei Fehler
            }
          }
        }
      };
      
      mediaRecorder.onerror = (event) => {
        console.error('MediaRecorder Fehler:', event);
        setError('Fehler beim Aufnehmen des Audios');
      };
      
      // Starte Aufnahme mit längeren Chunks für stabilere WebM-Dateien (alle 500ms)
      mediaRecorder.start(500);
      setIsRecording(true);
      
    } catch (error) {
      console.error('Streaming start error:', error);
      setError('Fehler beim Starten der Live-Transkription');
    }
  };

  const stopStreaming = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
    }
    
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    
    if (voskWSRef.current) {
      voskWSRef.current.stopStreaming();
      voskWSRef.current.disconnect();
      voskWSRef.current = null;
    }
    
    setIsRecording(false);
    setIsConnected(false);
  };

  const clearText = () => {
    setCurrentText('');
    setPartialText('');
  };

  // Cleanup beim Unmount
  useEffect(() => {
    return () => {
      stopStreaming();
    };
  }, []);

  return (
    <div className="space-y-4 p-6 bg-gradient-to-br from-blue-50 to-indigo-100 rounded-lg border border-blue-200">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-900">
          🎙️ Vosk Live-Transkription
        </h3>
        <div className="flex items-center space-x-2">
          {isConnected && (
            <div className="flex items-center text-green-600 text-sm">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse mr-2"></div>
              Verbunden
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-md">
          <p className="text-red-700 text-sm">{error}</p>
        </div>
      )}

      <div className="flex items-center space-x-3">
        {!modelLoaded ? (
          <Button
            onClick={loadModel}
            disabled={modelLoading}
            className="bg-blue-600 hover:bg-blue-700"
          >
            {modelLoading ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Lädt Vosk-Modell...
              </>
            ) : (
              <>
                <Play className="w-4 h-4 mr-2" />
                Vosk-Modell laden
              </>
            )}
          </Button>
        ) : (
          <>
            <Button
              onClick={isRecording ? stopStreaming : startStreaming}
              disabled={modelLoading}
              className={isRecording 
                ? "bg-red-600 hover:bg-red-700" 
                : "bg-green-600 hover:bg-green-700"
              }
            >
              {isRecording ? (
                <>
                  <Square className="w-4 h-4 mr-2" />
                  Stoppen
                </>
              ) : (
                <>
                  <Mic className="w-4 h-4 mr-2" />
                  Live-Streaming starten
                </>
              )}
            </Button>
            
            <Button
              onClick={clearText}
              variant="outline"
              disabled={isRecording}
            >
              Text löschen
            </Button>
          </>
        )}
      </div>

      {(currentText || partialText) && (
        <div className="space-y-3">
          <div className="p-4 bg-white rounded-lg border border-gray-200 shadow-sm">
            <h4 className="text-sm font-medium text-gray-700 mb-2">
              Transkribierter Text:
            </h4>
            <div className="space-y-2">
              {currentText && (
                <p className="text-gray-900 leading-relaxed">
                  {currentText}
                </p>
              )}
              {partialText && (
                <p className="text-gray-500 italic text-sm">
                  {partialText}
                  <span className="animate-pulse">|</span>
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="text-xs text-gray-500 space-y-1">
        <p>• Live-Streaming mit Vosk für kontinuierliche deutsche Spracherkennung</p>
        <p>• Optimiert für medizinische Fachbegriffe</p>
        <p>• Niedrige Latenz durch direktes Audio-Streaming</p>
      </div>
    </div>
  );
}
