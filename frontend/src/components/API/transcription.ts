import axios from "axios";

const API_BASE = "https://paul-schaefer-ms-7d75.tailf4012b.ts.net/api";

export async function getModels(): Promise<string[]> {
  const res = await axios.get(`${API_BASE}/api/models`);
  return res.data.models;
}

export async function transcribe(model: string, file: File): Promise<string[]> {
    const formData = new FormData();
    formData.append("model_name", model);
    formData.append("file", file);

    const res = await axios.post(`${API_BASE}/api/transcribe`, formData);
    return res.data.steps;
}

// Neue Funktion für Mikrofon-Audio (Blob oder File)
export async function transcribeAudioBlob(model: string, audioBlob: Blob): Promise<string[]> {
    const formData = new FormData();
    formData.append("model_name", model);
    // Wir geben einen Dateinamen an, falls audioBlob ein Blob ist
    formData.append("file", audioBlob, "microphone-audio.wav");

    const res = await axios.post(`${API_BASE}/api/transcribe`, formData);
    return res.data.steps;
}
