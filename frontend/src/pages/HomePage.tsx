import TranscriptionForm from "../components/AI-Speech/TranscriptionForm";

export const HomePage = () => {
  return (
    <main className="min-h-screen text-gray-900 dark:text-white py-10 px-4">
      <div className="max-w-3xl mx-auto space-y-8">
        <header className="text-center">
          <h1 className="text-3xl font-bold">🩺 Medizinische Sprach-zu-Text-Demo</h1>
          <p className="mt-2 text-gray-600 dark:text-gray-400 text-sm">
            Wählen Sie ein Modell, laden Sie eine Audiodatei hoch oder nehmen Sie direkt auf. Die KI transkribiert medizinische Sprache automatisch.
          </p>
        </header>

        <TranscriptionForm />
      </div>
    </main>
  );
};
