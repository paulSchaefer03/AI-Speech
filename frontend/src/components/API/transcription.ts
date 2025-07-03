import axios from "axios";

const API_BASE = "https://paul-schaefer-ms-7d75.tailf4012b.ts.net/api";
const API_BASE_LOCAL = "http://localhost:7860";
const API_BASE_USED =
  window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
    ? API_BASE_LOCAL
    : API_BASE;

export async function getModels(): Promise<string[]> {
  const res = await axios.get(`${API_BASE_USED}/api/models`);
  return res.data.models;
}

// Neue Funktion für Modell-Status
export async function getModelStatus(modelName: string): Promise<{loaded: boolean, loading: boolean}> {
  try {
    const res = await axios.get(`${API_BASE_USED}/api/model-status/${encodeURIComponent(modelName)}`);
    return res.data;
  } catch (error) {
    return {loaded: false, loading: false};
  }
}

// Funktion zum Vorladen eines Modells
export async function preloadModel(modelName: string): Promise<void> {
  await axios.post(`${API_BASE_USED}/api/preload-model`, {model_name: modelName});
}

export async function transcribe(model: string, file: File): Promise<string[]> {
    const formData = new FormData();
    formData.append("model_name", model);
    formData.append("file", file);

    const res = await axios.post(`${API_BASE_USED}/api/transcribe`, formData);
    return res.data.steps;
}

// Neue Funktion für Mikrofon-Audio (Blob oder File)
export async function transcribeAudioBlob(model: string, audioBlob: Blob): Promise<string[]> {
    const formData = new FormData();
    formData.append("model_name", model);
    // Wir geben einen Dateinamen an, falls audioBlob ein Blob ist
    formData.append("file", audioBlob, "microphone-audio.wav");

    const res = await axios.post(`${API_BASE_USED}/api/transcribe`, formData);
    return res.data.steps;
}

// WebSocket-Klasse für Live-Transkription
export class LiveTranscription {
  private ws: WebSocket | null = null;
  private onTranscription: (text: string, chunkId: string) => void;
  private onError: (error: string) => void;
  private onConnect: () => void;
  private onDisconnect: () => void;

  constructor(
    onTranscription: (text: string, chunkId: string) => void,
    onError: (error: string) => void,
    onConnect: () => void,
    onDisconnect: () => void
  ) {
    this.onTranscription = onTranscription;
    this.onError = onError;
    this.onConnect = onConnect;
    this.onDisconnect = onDisconnect;
  }

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        // Korrekte WebSocket-URL basierend auf API_BASE_USED erstellen
        let wsUrl = API_BASE_USED.replace("https://", "wss://").replace("http://", "ws://");
        const fullWsUrl = `${wsUrl}/api/transcribe-live`;
        console.log("WebSocket-Verbindung wird hergestellt:", fullWsUrl);
        this.ws = new WebSocket(fullWsUrl);

        this.ws.onopen = () => {
          this.onConnect();
          resolve();
        };

        this.ws.onmessage = (event) => {
          const data = JSON.parse(event.data);
          
          if (data.type === "transcription") {
            this.onTranscription(data.text, data.chunk_id);
          } else if (data.type === "error") {
            this.onError(data.message);
          }
        };

        this.ws.onclose = () => {
          this.onDisconnect();
        };

        this.ws.onerror = (error) => {
          this.onError("WebSocket-Verbindungsfehler");
          reject(error);
        };
      } catch (error) {
        reject(error);
      }
    });
  }

  sendAudioChunk(audioBlob: Blob, model: string, chunkId: string): Promise<void> {
    return new Promise((resolve, reject) => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
        reject(new Error("WebSocket nicht verbunden"));
        return;
      }

      const reader = new FileReader();
      reader.onload = () => {
        const arrayBuffer = reader.result as ArrayBuffer;
        const base64Audio = base64ArrayBuffer(arrayBuffer);
;
        
        this.ws!.send(JSON.stringify({
          type: "audio_chunk",
          audio: base64Audio,
          model: model,
          chunk_id: chunkId
        }));
        
        resolve();
      };
      
      reader.onerror = () => reject(new Error("Fehler beim Lesen der Audiodaten"));
      reader.readAsArrayBuffer(audioBlob);
    });
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}

// WebSocket-Klasse für Vosk Live-Streaming-Transkription
export class VoskLiveTranscription {
  private ws: WebSocket | null = null;
  private onTranscription: (text: string, partial: boolean, confidence: number) => void;
  private onError: (error: string) => void;
  private onConnect: () => void;
  private onDisconnect: () => void;

  constructor(
    onTranscription: (text: string, partial: boolean, confidence: number) => void,
    onError: (error: string) => void,
    onConnect: () => void,
    onDisconnect: () => void
  ) {
    this.onTranscription = onTranscription;
    this.onError = onError;
    this.onConnect = onConnect;
    this.onDisconnect = onDisconnect;
  }

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        // Korrekte WebSocket-URL für Vosk-Streaming
        let wsUrl = API_BASE_USED.replace("https://", "wss://").replace("http://", "ws://");
        const fullWsUrl = `${wsUrl}/api/transcribe-vosk-stream`;
        console.log("Vosk WebSocket-Verbindung wird hergestellt:", fullWsUrl);
        this.ws = new WebSocket(fullWsUrl);

        this.ws.onopen = () => {
          this.onConnect();
          resolve();
        };

        this.ws.onmessage = (event) => {
          const data = JSON.parse(event.data);
          
          if (data.type === "transcription") {
            this.onTranscription(data.text, data.partial || false, data.confidence || 0);
          } else if (data.type === "error") {
            this.onError(data.message);
          }
        };

        this.ws.onclose = () => {
          this.onDisconnect();
        };

        this.ws.onerror = (error) => {
          this.onError("Vosk WebSocket-Verbindungsfehler");
          reject(error);
        };
      } catch (error) {
        reject(error);
      }
    });
  }

  sendAudioChunk(audioBlob: Blob): Promise<void> {
    return new Promise((resolve, reject) => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
        reject(new Error("Vosk WebSocket nicht verbunden"));
        return;
      }

      const reader = new FileReader();
      reader.onload = () => {
        const arrayBuffer = reader.result as ArrayBuffer;
        const base64Audio = base64ArrayBuffer(arrayBuffer);
        
        this.ws!.send(JSON.stringify({
          type: "audio_chunk",
          audio: base64Audio
        }));
        
        resolve();
      };
      
      reader.onerror = () => reject(new Error("Fehler beim Lesen der Vosk-Audiodaten"));
      reader.readAsArrayBuffer(audioBlob);
    });
  }

  stopStreaming() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: "stop_stream"
      }));
    }
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}

function base64ArrayBuffer(arrayBuffer: ArrayBuffer): string {
  const bytes = new Uint8Array(arrayBuffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}
