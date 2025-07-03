import { useEffect, useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { getModels, transcribeAudioBlob, LiveTranscription } from "../API/transcription";
import ModelSelector from "./ModelSelector";
import AudioUploader from "./AudioUploader";
import TranscriptionOutput from "./TranscriptionOutput";
import AudioVisualizer from "./AudioVisualizer";

export default function TranscriptionForm() {
  const [models, setModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [file, setFile] = useState<File | null>(null);
  const [output, setOutput] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isLiveMode, setIsLiveMode] = useState(false);
  const [liveTranscription, setLiveTranscription] = useState<string[]>([]);
  const [liveTranscriptionText, setLiveTranscriptionText] = useState<string>("");
  const [connectionStatus, setConnectionStatus] = useState<"disconnected" | "connecting" | "connected">("disconnected");
  
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const liveMediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const liveTranscriptionRef = useRef<LiveTranscription | null>(null);
  const audioChunkIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    getModels().then((models) => {
      setModels(models);
      setSelectedModel(models[0]);
    });
  }, []);

  const handleSubmit = async () => {
    const audioToSend = file ?? audioBlob;
    if (!audioToSend || !selectedModel) return;

    setLoading(true);
    setOutput([]);

    try {
      const steps = await transcribeAudioBlob(selectedModel, audioToSend);
      setOutput(steps);
    } catch (e) {
      setOutput(["❌ Fehler beim Senden der Anfrage."]);
    } finally {
      setLoading(false);
    }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      
      if (isLiveMode) {
        // Live-Modus: WebSocket-Verbindung aufbauen
        setConnectionStatus("connecting");
        const liveTranscription = new LiveTranscription(
          (text: string, chunkId: string) => {
            if (text.trim()) {
              // Füge den neuen Text am Ende hinzu mit einem Leerzeichen als Trenner
              setLiveTranscriptionText(prev => {
                const newText = prev ? `${prev} ${text.trim()}` : text.trim();
                return newText;
              });
              
              // Behalte auch die Chunk-Liste für Debug-Zwecke (optional)
              setLiveTranscription(prev => [...prev, text.trim()]);
            }
          },
          (error: string) => {
            console.error("Live-Transkription Fehler:", error);
            setOutput(prev => [...prev, `❌ ${error}`]);
          },
          () => {
            console.log("Live-Transcription connected");
            setConnectionStatus("connected");
          },
          () => {
            console.log("Live-Transcription disconnected");
            setConnectionStatus("disconnected");
          }
        );
        
        liveTranscriptionRef.current = liveTranscription;
        await liveTranscription.connect();
        
        // Audio-Chunks in regelmäßigen Abständen senden (alle 5 Sekunden)
        const sendAudioChunks = () => {
          if (!streamRef.current) return;
          
          console.log("Starting new audio chunk recording...");
          
          // Überprüfe unterstützte MIME-Types und bevorzuge kompatiblere Formate
          let mimeType = "";
          const preferredTypes = [
            "audio/wav",
            "audio/webm;codecs=pcm",
            "audio/webm;codecs=opus", 
            "audio/webm",
            "audio/mp4",
            "audio/ogg"
          ];
          
          for (const type of preferredTypes) {
            if (MediaRecorder.isTypeSupported(type)) {
              mimeType = type;
              break;
            }
          }
          
          console.log("Using MIME type:", mimeType);
          const mediaRecorder = mimeType ? 
            new MediaRecorder(streamRef.current, { mimeType }) : 
            new MediaRecorder(streamRef.current);
          
          liveMediaRecorderRef.current = mediaRecorder;
          let chunks: Blob[] = [];
          
          mediaRecorder.ondataavailable = (e) => {
            console.log("Audio data available:", e.data.size, "bytes", "type:", e.data.type);
            if (e.data.size > 0) {
              chunks.push(e.data);
            }
          };
          
          mediaRecorder.onstop = async () => {
            console.log("MediaRecorder stopped, chunks:", chunks.length);
            if (chunks.length > 0) {
              const audioBlob = new Blob(chunks, { 
                type: mimeType || "audio/webm" 
              });
              const chunkId = `chunk_${Date.now()}`;
              
              console.log("Sending audio chunk:", audioBlob.size, "bytes");
              
              try {
                await liveTranscription.sendAudioChunk(audioBlob, selectedModel, chunkId);
                console.log("Audio chunk sent successfully");
              } catch (error) {
                console.error("Fehler beim Senden des Audio-Chunks:", error);
              }
            } else {
              console.warn("No audio chunks to send");
            }
            
            // Plane den nächsten Chunk, aber nur wenn noch aufgenommen wird
            if (liveMediaRecorderRef.current === mediaRecorder) {
              setTimeout(() => {
                if (streamRef.current && liveTranscriptionRef.current) {
                  sendAudioChunks();
                }
              }, 1000); // 1 Sekunde Pause zwischen Chunks
            }
          };
          
          mediaRecorder.onerror = (e) => {
            console.error("MediaRecorder error:", e);
          };
          
          // Starte Aufnahme und stoppe nach 5 Sekunden
          mediaRecorder.start();
          console.log("MediaRecorder started, will stop after 5 seconds");
          
          setTimeout(() => {
            if (mediaRecorder.state === "recording") {
              mediaRecorder.stop();
            }
          }, 5000);
        };
        
        setIsRecording(true);
        setLiveTranscription([]);
        setLiveTranscriptionText(""); // Setze den kombinierten Text zurück
        sendAudioChunks();
        
      } else {
        // Normaler Modus: Komplette Aufnahme
        const mediaRecorder = new MediaRecorder(stream);
        mediaRecorderRef.current = mediaRecorder;
        chunksRef.current = [];

        mediaRecorder.ondataavailable = (e) => {
          chunksRef.current.push(e.data);
        };

        mediaRecorder.onstop = () => {
          const blob = new Blob(chunksRef.current, { type: "audio/webm" });
          setAudioBlob(blob);
          setFile(null);
          setIsRecording(false);
        };

        mediaRecorder.start();
        setIsRecording(true);
      }
    } catch (err) {
      console.error("Fehler bei der Aufnahme:", err);
      setIsRecording(false);
      setConnectionStatus("disconnected");
    }
  };

  const stopRecording = () => {
    setIsRecording(false);
    
    if (isLiveMode) {
      // Live-Modus: MediaRecorder und WebSocket-Verbindung schließen
      if (liveMediaRecorderRef.current && liveMediaRecorderRef.current.state !== "inactive") {
        console.log("Stopping live MediaRecorder");
        liveMediaRecorderRef.current.stop();
      }
      
      // Wichtig: MediaRecorder-Referenz löschen, um Rekursion zu stoppen
      liveMediaRecorderRef.current = null;
      
      if (liveTranscriptionRef.current) {
        liveTranscriptionRef.current.disconnect();
        liveTranscriptionRef.current = null;
      }
      setConnectionStatus("disconnected");
      
      // Übertrage den finalen Live-Text in die normale Ausgabe für weitere Verwendung
      if (liveTranscriptionText.trim()) {
        setOutput([
          "🔴 Live-Transkription abgeschlossen:",
          `✅ Final: ${liveTranscriptionText.trim()}`
        ]);
      }
    } else {
      // Normaler Modus: MediaRecorder stoppen
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
        mediaRecorderRef.current.stop();
      }
    }
    
    // Stream aufräumen
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
  };

 return (
    <section className="max-w-2xl mx-auto p-4">
      {/* Live-Modus Toggle */}
      <div className="flex items-center justify-center gap-4 mb-6 p-4 rounded-lg bg-gray-100 dark:bg-gray-800">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={isLiveMode}
            onChange={(e) => setIsLiveMode(e.target.checked)}
            disabled={isRecording}
            className="rounded"
          />
          <span className="text-sm font-medium">
            🔴 Live-Transkription (experimentell)
          </span>
        </label>
        {isLiveMode && (
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${
              connectionStatus === "connected" ? "bg-green-500" : 
              connectionStatus === "connecting" ? "bg-yellow-500" : "bg-red-500"
            }`}></div>
            <span className="text-xs text-gray-600 dark:text-gray-400">
              {connectionStatus === "connected" ? "Verbunden" : 
               connectionStatus === "connecting" ? "Verbinde..." : "Getrennt"}
            </span>
          </div>
        )}
      </div>

      {/* Aufnahme-Buttons */}
      <div className="flex flex-col sm:flex-row justify-center gap-4 mb-6">
        <motion.button
          whileTap={{ scale: 0.95 }}
          onClick={startRecording}
          disabled={isRecording}
          className="px-5 py-2 rounded-xl bg-green-500 text-white font-medium disabled:opacity-50"
        >
          🎙 {isLiveMode ? "Live-Aufnahme starten" : "Aufnahme starten"}
        </motion.button>
        <motion.button
          whileTap={{ scale: 0.95 }}
          onClick={stopRecording}
          disabled={!isRecording}
          className="px-5 py-2 rounded-xl bg-red-500 text-white font-medium disabled:opacity-50"
        >
          ⏹️ Aufnahme stoppen
        </motion.button>
      </div>

      {/* Aufnahme-Indikator */}
      <AudioVisualizer isRecording={isRecording} />

      {/* Modellauswahl */}
      <div className="mb-4">
        <ModelSelector
          models={models}
          selected={selectedModel}
          onChange={setSelectedModel}
        />
      </div>

      {/* Audio Upload - nur im normalen Modus */}
      {!isLiveMode && (
        <div className="mb-6">
          <AudioUploader
            onFileSelected={(f) => {
              setFile(f);
              setAudioBlob(null);
            }}
          />
        </div>
      )}

      {/* Live-Transkription Anzeige */}
      {isLiveMode && liveTranscriptionText && (
        <div className="mb-6">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-lg font-semibold">🔴 Live-Transkription:</h3>
            <button
              onClick={() => {
                navigator.clipboard.writeText(liveTranscriptionText);
              }}
              className="text-xs bg-gray-200 dark:bg-gray-700 px-2 py-1 rounded hover:bg-gray-300 dark:hover:bg-gray-600"
              title="Text kopieren"
            >
              📋 Kopieren
            </button>
          </div>
          <div className="bg-blue-50 dark:bg-blue-900/20 p-4 rounded-lg border-l-4 border-blue-500 max-h-60 overflow-y-auto">
            <p className="text-sm text-blue-800 dark:text-blue-200 leading-relaxed whitespace-pre-wrap">
              {liveTranscriptionText}
              {isRecording && <span className="animate-pulse">|</span>}
            </p>
          </div>
          
          {/* Debug-Bereich (optional, kann entfernt werden) */}
          {process.env.NODE_ENV === 'development' && liveTranscription.length > 0 && (
            <details className="mt-2">
              <summary className="text-xs text-gray-500 cursor-pointer">Debug: Chunks anzeigen ({liveTranscription.length})</summary>
              <div className="mt-2 text-xs text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 p-2 rounded">
                {liveTranscription.map((chunk, index) => (
                  <div key={index} className="mb-1">
                    <span className="font-mono">Chunk {index + 1}:</span> {chunk}
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      )}

      {/* Hinweis wenn Live-Modus aktiv aber noch kein Text */}
      {isLiveMode && !liveTranscriptionText && isRecording && (
        <div className="mb-6">
          <div className="bg-yellow-50 dark:bg-yellow-900/20 p-4 rounded-lg border-l-4 border-yellow-500">
            <p className="text-sm text-yellow-800 dark:text-yellow-200">
              🎙️ Live-Aufnahme läuft... Sprechen Sie deutlich, die Transkription erscheint in Kürze.
            </p>
          </div>
        </div>
      )}

      {/* Transkribieren - nur im normalen Modus */}
      {!isLiveMode && (
        <div className="text-center mb-8">
          <button
            onClick={handleSubmit}
            disabled={loading || (!file && !audioBlob)}
            className="px-6 py-2 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "⏳ Transkribiere…" : "📝 Transkribieren"}
          </button>
        </div>
      )}

      {/* Normale Transkription Ausgabe - nur im normalen Modus ODER nach Live-Session */}
      {!isLiveMode && <TranscriptionOutput lines={output} />}
      
      {/* Zeige auch normale Ausgabe im Live-Modus wenn Session beendet */}
      {isLiveMode && !isRecording && output.length > 0 && (
        <div className="mt-6">
          <TranscriptionOutput lines={output} />
        </div>
      )}
    </section>
  );
}