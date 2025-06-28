import React from "react";

export default function AudioUploader({
  onFileSelected,
}: {
  onFileSelected: (file: File | null) => void;
}) {
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);
  const [uploadedFile, setUploadedFile] = React.useState<File | null>(null);

  const handleFile = (file: File | null) => {
    setUploadedFile(file);
    onFileSelected(file);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  const handleButtonClick = () => {
    fileInputRef.current?.click();
  };

  return (
    <div
      className="flex flex-col gap-2"
      style={{
        padding: "10px",
        borderRadius: "5px",
        border: "1px solid var(--color-border)",
        background: "var(--color-background-transcribed)",
        color: "var(--color-text-transcribed)",
        outline: "none",
      }}
    >
      <label className="text-sm font-medium text-muted-foreground mb-2">
        🎧 Audiodatei hochladen (.wav)
      </label>

      <button
        type="button"
        onClick={handleButtonClick}
        className="mb-2 px-4 py-2 rounded bg-primary text-white hover:bg-primary/80"
        style={{
          background: "var(--color-input, #2563eb)",
          color: "var(--color-on-primary, #fff)",
          transition: "background 0.2s, color 0.2s",
        }}
      >
        Durchsuchen...
      </button>

      <input
        ref={fileInputRef}
        type="file"
        accept="audio/wav"
        onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
        style={{ display: "none" }}
      />

      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        className="flex items-center justify-center border-2 border-dashed border-gray-400 rounded p-4 text-center cursor-pointer"
        style={{
          background: "var(--color-background-transcribed)",
          color: "var(--color-text-transcribed)",
          border: "2px dashed var(--color-border)",
        }}
        onClick={handleButtonClick}
      >
        {uploadedFile ? (
          <span className="text-green-600 font-semibold flex items-center gap-2">
            <svg width="20" height="20" fill="none" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="12" fill="#22c55e" />
              <path
                d="M7 13l3 3 7-7"
                stroke="#fff"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            {uploadedFile.name} hochgeladen
          </span>
        ) : (
          "Hier Ablegen"
        )}
      </div>
    </div>
  );
}
