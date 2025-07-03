import React, { useState, useRef, useEffect } from 'react';
import { Mic, Square, Loader2, Settings } from 'lucide-react';
import { Button } from '../ui/button';
import { VoskLiveTranscription as VoskWebSocket, preloadModel, getModelStatus } from '../API/transcription';

interface VoskPCMTranscriptionProps {
  onTranscription?: (text: string, partial: boolean, confidence: number) => void;
}

export function VoskPCMTranscription({ onTranscription }: VoskPCMTranscriptionProps) {
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

  const createWAVHeader = (sampleRate: number, numChannels: number, bitsPerSample: number, dataLength: number): ArrayBuffer => {
    const header = new ArrayBuffer(44);
    const view = new DataView(header);
    
    // WAV-Header schreiben
    const writeString = (offset: number, string: string) => {
      for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
      }
    };
    
    writeString(0, 'RIFF');
    view.setUint32(4, 36 + dataLength, true);
    writeString(8, 'WAVE');
    writeString(12, 'fmt ');
    view.setUint32(16, 16, true); // PCM chunk size
    view.setUint16(20, 1, true); // PCM format
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * numChannels * bitsPerSample / 8, true); // Byte rate
    view.setUint16(32, numChannels * bitsPerSample / 8, true); // Block align
    view.setUint16(34, bitsPerSample, true);
    writeString(36, 'data');
    view.setUint32(40, dataLength, true);
    
    return header;
  };

  const float32ToPCM16 = (float32Array: Float32Array): Int16Array => {
    const pcm16 = new Int16Array(float32Array.length);
    for (let i = 0; i < float32Array.length; i++) {
      const sample = Math.max(-1, Math.min(1, float32Array[i]));
      pcm16[i] = sample * 0x7FFF;
    }
    return pcm16;
  };

  const startPCMStreaming = async () => {
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
      
      // Ermittle die Stream-Sample-Rate
      const track = stream.getAudioTracks()[0];
      const settings = track.getSettings();
      const streamSampleRate = settings.sampleRate || 44100;
      
      console.log(`PCM Stream sample rate: ${streamSampleRate}Hz`);
      
      // Audio-Context mit Stream-Sample-Rate
      audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)({
        sampleRate: streamSampleRate
      });
      
      // WebSocket-Verbindung
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
      
      // Audio-Source und Processor
      sourceRef.current = audioContextRef.current.createMediaStreamSource(stream);
      const bufferSize = 4096;
      processorRef.current = audioContextRef.current.createScriptProcessor(bufferSize, 1, 1);
      
      let audioBuffer: Float32Array[] = [];
      const targetSamples = Math.floor(streamSampleRate * 0.5); // 0.5 Sekunden
      
      processorRef.current.onaudioprocess = async (event) => {
        const inputBuffer = event.inputBuffer;
        const inputData = inputBuffer.getChannelData(0);
        
        // Sammle Audio-Daten
        audioBuffer.push(new Float32Array(inputData));
        
        const totalSamples = audioBuffer.reduce((sum, chunk) => sum + chunk.length, 0);
        
        if (totalSamples >= targetSamples) {
          // Kombiniere Audio-Daten
          const combinedData = new Float32Array(totalSamples);
          let offset = 0;
          
          for (const chunk of audioBuffer) {
            combinedData.set(chunk, offset);
            offset += chunk.length;
          }
          
          // Resample zu 16kHz für Vosk
          const resampledData = resampleAudio(combinedData, streamSampleRate, 16000);
          
          // Konvertiere zu 16-bit PCM
          const pcm16 = float32ToPCM16(resampledData);
          
          // Erstelle WAV-Datei
          const wavHeader = createWAVHeader(16000, 1, 16, pcm16.length * 2);
          const wavData = new Uint8Array(wavHeader.byteLength + pcm16.length * 2);
          wavData.set(new Uint8Array(wavHeader), 0);
          wavData.set(new Uint8Array(pcm16.buffer), wavHeader.byteLength);
          
          const wavBlob = new Blob([wavData], { type: 'audio/wav' });
          
          if (voskWSRef.current && wavBlob.size > 0) {
            try {
              console.log(`Sending PCM WAV chunk: ${wavBlob.size} bytes (16kHz)`);
              await voskWSRef.current.sendAudioChunk(wavBlob);
            } catch (error) {
              console.error('Fehler beim Senden von PCM-Chunk:', error);
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
      console.error('PCM streaming error:', error);
      setError('Fehler beim Starten der PCM-Transkription');
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
      
      result[i] = audioData[indexFloor] * (1 - t) + audioData[indexCeil] * t;
    }
    
    return result;
  };

  const stopStreaming = () => {
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

  return (
    <div className="w-full max-w-4xl mx-auto p-6 bg-white rounded-lg shadow-lg">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold text-gray-800">
          Vosk PCM Live-Transkription
        </h2>
        <div className="flex items-center space-x-2">
          {!modelLoaded && (
            <Button
              onClick={loadModel}
              disabled={modelLoading}
              size="sm"
              variant="outline"
            >
              {modelLoading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Lädt...
                </>
              ) : (
                <>
                  <Settings className="w-4 h-4 mr-2" />
                  Modell laden
                </>
              )}
            </Button>
          )}
          
          <div className={`px-3 py-1 rounded-full text-sm font-medium ${
            isConnected ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'
          }`}>
            {isConnected ? 'Verbunden' : 'Getrennt'}
          </div>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-100 border border-red-400 text-red-700 rounded">
          {error}
        </div>
      )}

      <div className="flex justify-center mb-6">
        <Button
          onClick={isRecording ? stopStreaming : startPCMStreaming}
          disabled={!modelLoaded || modelLoading}
          size="lg"
          className={`px-8 py-4 ${
            isRecording ? 'bg-red-500 hover:bg-red-600' : 'bg-blue-500 hover:bg-blue-600'
          }`}
        >
          {isRecording ? (
            <>
              <Square className="w-6 h-6 mr-2" />
              Stoppen
            </>
          ) : (
            <>
              <Mic className="w-6 h-6 mr-2" />
              PCM-Aufnahme starten
            </>
          )}
        </Button>
      </div>

      <div className="space-y-4">
        {partialText && (
          <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
            <p className="text-sm text-yellow-600 mb-1">Zwischenergebnis:</p>
            <p className="text-gray-700 italic">{partialText}</p>
          </div>
        )}

        <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg min-h-[100px]">
          <p className="text-sm text-gray-600 mb-2">Erkannter Text:</p>
          <p className="text-gray-800 whitespace-pre-wrap">
            {currentText || 'Keine Transkription verfügbar...'}
          </p>
        </div>
      </div>

      <div className="mt-4 text-sm text-gray-500">
        <p><strong>PCM-Verfahren:</strong> Direkte WAV/PCM-Übertragung ohne WebM-Konvertierung</p>
        <p><strong>Vorteile:</strong> Keine fragmentierten Container, bessere Kompatibilität</p>
      </div>
    </div>
  );
}
