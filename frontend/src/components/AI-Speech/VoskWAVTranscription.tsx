import React, { useState, useRef, useEffect } from 'react';
import { Mic, Square, Loader2 } from 'lucide-react';
import { Button } from '../ui/button';
import { VoskLiveTranscription as VoskWebSocket, preloadModel, getModelStatus } from '../API/transcription';

interface VoskWAVTranscriptionProps {
  onTranscription?: (text: string, partial: boolean, confidence: number) => void;
}

export function VoskWAVTranscription({ onTranscription }: VoskWAVTranscriptionProps) {
  const [isRecording, setIsRecording] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [modelLoading, setModelLoading] = useState(false);
  const [modelLoaded, setModelLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentText, setCurrentText] = useState('');
  const [partialText, setPartialText] = useState('');
  
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const voskWSRef = useRef<VoskWebSocket | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);

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

  const createWAVChunk = (audioData: Float32Array, sampleRate: number = 16000): Blob => {
    const length = audioData.length;
    const buffer = new ArrayBuffer(44 + length * 2);
    const view = new DataView(buffer);
    
    // WAV-Header schreiben
    const writeString = (offset: number, string: string) => {
      for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
      }
    };
    
    writeString(0, 'RIFF');
    view.setUint32(4, 36 + length * 2, true);
    writeString(8, 'WAVE');
    writeString(12, 'fmt ');
    view.setUint32(16, 16, true); // Chunk size
    view.setUint16(20, 1, true); // PCM format
    view.setUint16(22, 1, true); // Mono
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true); // Byte rate
    view.setUint16(32, 2, true); // Block align
    view.setUint16(34, 16, true); // Bits per sample
    writeString(36, 'data');
    view.setUint32(40, length * 2, true);
    
    // PCM-Daten konvertieren (Float32 zu Int16)
    let offset = 44;
    for (let i = 0; i < length; i++) {
      const sample = Math.max(-1, Math.min(1, audioData[i]));
      view.setInt16(offset, sample * 0x7FFF, true);
      offset += 2;
    }
    
    return new Blob([buffer], { type: 'audio/wav' });
  };

  const startWAVStreaming = async () => {
    if (!modelLoaded) {
      await loadModel();
      if (!modelLoaded) return;
    }

    try {
      setError(null);
      
      // Mikrofon-Stream anfordern
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });
      
      streamRef.current = stream;
      
      // Ermittle die tatsächliche Sample-Rate des Streams
      const track = stream.getAudioTracks()[0];
      const settings = track.getSettings();
      const streamSampleRate = settings.sampleRate || 44100;
      
      console.log(`WAV Stream sample rate: ${streamSampleRate}Hz`);
      
      // Audio-Context mit der Stream-Sample-Rate erstellen
      audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)({
        sampleRate: streamSampleRate
      });
      
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
      
      // Audio-Source erstellen
      sourceRef.current = audioContextRef.current.createMediaStreamSource(stream);
      
      // Script Processor für Audio-Verarbeitung
      const bufferSize = 4096;
      processorRef.current = audioContextRef.current.createScriptProcessor(bufferSize, 1, 1);
      
      let audioBuffer: Float32Array[] = [];
      const targetSamples = Math.floor(streamSampleRate * 1.0); // 1 Sekunde
      
      processorRef.current.onaudioprocess = async (event) => {
        const inputBuffer = event.inputBuffer;
        const inputData = inputBuffer.getChannelData(0);
        
        // Sammle Audio-Daten
        audioBuffer.push(new Float32Array(inputData));
        
        // Berechne gesammelte Samples
        const totalSamples = audioBuffer.reduce((sum, chunk) => sum + chunk.length, 0);
        
        // Wenn genug Samples gesammelt, sende WAV-Chunk
        if (totalSamples >= targetSamples) {
          // Kombiniere alle gesammelten Chunks
          const combinedData = new Float32Array(totalSamples);
          let offset = 0;
          
          for (const chunk of audioBuffer) {
            combinedData.set(chunk, offset);
            offset += chunk.length;
          }
          
          // Resample zu 16kHz für Vosk wenn nötig
          let processedData = combinedData;
          
          if (streamSampleRate !== 16000) {
            processedData = resampleAudio(combinedData, streamSampleRate, 16000);
          }
          
          // Konvertiere zu WAV und sende
          const wavBlob = createWAVChunk(processedData, 16000);
          
          if (voskWSRef.current && wavBlob.size > 0) {
            try {
              console.log(`Sending WAV chunk: ${wavBlob.size} bytes (${streamSampleRate}Hz -> 16kHz)`);
              await voskWSRef.current.sendAudioChunk(wavBlob);
            } catch (error) {
              console.error('Fehler beim Senden von WAV-Chunk:', error);
            }
          }
          
          // Reset buffer
          audioBuffer = [];
        }
      };
      
      // Verbinde Audio-Pipeline
      sourceRef.current.connect(processorRef.current);
      processorRef.current.connect(audioContextRef.current.destination);
      
      setIsRecording(true);
      
    } catch (error) {
      console.error('WAV streaming error:', error);
      setError('Fehler beim Starten der WAV-Transkription');
    }
  };

  const resampleAudio = (audioData: Float32Array, fromSampleRate: number, toSampleRate: number): Float32Array => {
    if (fromSampleRate === toSampleRate) {
      return audioData;
    }
    
    const ratio = fromSampleRate / toSampleRate;
    const newLength = Math.floor(audioData.length / ratio);
    const result = new Float32Array(newLength);
    
    for (let i = 0; i < newLength; i++) {
      const index = i * ratio;
      const indexFloor = Math.floor(index);
      const indexCeil = Math.min(indexFloor + 1, audioData.length - 1);
      const t = index - indexFloor;
      
      // Lineare Interpolation
      result[i] = audioData[indexFloor] * (1 - t) + audioData[indexCeil] * t;
    }
    
    return result;
  };

  const stopWAVStreaming = () => {
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    
    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }
    
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    
    if (voskWSRef.current) {
      voskWSRef.current.disconnect();
      voskWSRef.current = null;
    }
    
    setIsRecording(false);
    setIsConnected(false);
  };

  const toggleRecording = async () => {
    if (isRecording) {
      stopWAVStreaming();
    } else {
      await startWAVStreaming();
    }
  };

  return (
    <div className="p-6 border rounded-lg shadow-sm bg-white">
      <div className="mb-4">
        <h3 className="text-lg font-semibold mb-2">Vosk WAV Live Transcription</h3>
        <p className="text-sm text-gray-600">
          Alternative WAV-basierte Live-Transkription (vermeidet WebM-Probleme)
        </p>
      </div>

      <div className="space-y-4">
        {/* Model Status */}
        <div className="flex items-center space-x-2">
          {modelLoading ? (
            <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
          ) : modelLoaded ? (
            <div className="w-3 h-3 bg-green-500 rounded-full"></div>
          ) : (
            <div className="w-3 h-3 bg-red-500 rounded-full"></div>
          )}
          <span className="text-sm">
            Vosk-Modell: {modelLoading ? 'Lädt...' : modelLoaded ? 'Bereit' : 'Nicht geladen'}
          </span>
          {!modelLoaded && !modelLoading && (
            <Button size="sm" variant="outline" onClick={loadModel}>
              Modell laden
            </Button>
          )}
        </div>

        {/* Connection Status */}
        {modelLoaded && (
          <div className="flex items-center space-x-2">
            <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-500' : 'bg-gray-400'}`}></div>
            <span className="text-sm">
              WebSocket: {isConnected ? 'Verbunden' : 'Getrennt'}
            </span>
          </div>
        )}

        {/* Control Button */}
        <Button
          onClick={toggleRecording}
          disabled={!modelLoaded}
          className={`w-full ${isRecording ? 'bg-red-500 hover:bg-red-600' : 'bg-blue-500 hover:bg-blue-600'}`}
        >
          {isRecording ? (
            <>
              <Square className="w-4 h-4 mr-2" />
              WAV-Aufnahme stoppen
            </>
          ) : (
            <>
              <Mic className="w-4 h-4 mr-2" />
              WAV-Aufnahme starten
            </>
          )}
        </Button>

        {/* Error Display */}
        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded text-red-700 text-sm">
            {error}
          </div>
        )}

        {/* Transcription Results */}
        {(currentText || partialText) && (
          <div className="space-y-2">
            <h4 className="font-semibold text-sm">Transkription:</h4>
            <div className="p-3 bg-gray-50 border rounded min-h-[100px]">
              <div className="text-gray-900">{currentText}</div>
              {partialText && (
                <div className="text-gray-500 italic">{partialText}</div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
