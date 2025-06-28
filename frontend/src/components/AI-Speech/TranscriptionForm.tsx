import { useEffect, useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { getModels, transcribeAudioBlob } from "../API/transcription";
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
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

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
    } catch (err) {
      console.error("Fehler bei der Aufnahme:", err);
      setIsRecording(false);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
    }
  };

 return (
    <section className="max-w-2xl mx-auto p-4">
      {/* Aufnahme-Buttons */}
      <div className="flex flex-col sm:flex-row justify-center gap-4 mb-6">
        <motion.button
          whileTap={{ scale: 0.95 }}
          onClick={startRecording}
          disabled={isRecording}
          className="px-5 py-2 rounded-xl bg-green-500 text-white font-medium disabled:opacity-50"
        >
          🎙 Aufnahme starten
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

      {/* Audio Upload */}
      <div className="mb-6">
        <AudioUploader
          onFileSelected={(f) => {
            setFile(f);
            setAudioBlob(null);
          }}
        />
      </div>

      {/* Transkribieren */}
      <div className="text-center mb-8">
        <button
          onClick={handleSubmit}
          disabled={loading}
          className="px-6 py-2 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "⏳ Transkribiere…" : "📝 Transkribieren"}
        </button>
      </div>

      <TranscriptionOutput lines={output} />
    </section>
  );
}