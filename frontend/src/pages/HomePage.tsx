import TranscriptionForm from "../components/AI-Speech/TranscriptionForm";
import { VoskLiveTranscription } from "../components/AI-Speech/VoskLiveTranscription";
import { VoskWebAudioTranscription } from "../components/AI-Speech/VoskWebAudioTranscription";

export const HomePage = () => {
  return (
    <main className="min-h-screen text-gray-900 dark:text-white py-10 px-4">
      <div className="max-w-5xl mx-auto space-y-8">
        <header className="text-center">
          <h1 className="text-3xl font-bold">🩺 Medizinische Sprach-zu-Text-Demo</h1>
          <p className="mt-2 text-gray-600 dark:text-gray-400 text-sm">
            Wählen Sie ein Modell, laden Sie eine Audiodatei hoch oder nutzen Sie Live-Streaming. Die KI transkribiert medizinische Sprache automatisch.
          </p>
        </header>

        {/* Vosk Live-Streaming Sections */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
            <VoskLiveTranscription 
              onTranscription={(text, partial, confidence) => {
                console.log('Vosk MediaRecorder Transcription:', { text, partial, confidence });
              }}
            />
          </div>
          
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
            <VoskWebAudioTranscription 
              onTranscription={(text, partial, confidence) => {
                console.log('Vosk Web Audio Transcription:', { text, partial, confidence });
              }}
            />
          </div>
        </div>

        {/* Standard Transcription Form */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
          <h2 className="text-xl font-semibold mb-4">📁 Standard Transkription</h2>
          <TranscriptionForm />
        </div>
      </div>
    </main>
  );
};
