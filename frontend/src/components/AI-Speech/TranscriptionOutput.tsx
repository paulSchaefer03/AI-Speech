import React from "react";

export default function TranscriptionOutput({ lines }: { lines: string[] }) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <h3 style={{ fontSize: "1rem", margin: 0 }}>Transkribierter Text:</h3>
        <button
          style={{
            padding: "6px 16px",
            background: "var(--color-input)",
            color: "var(--color-text-button, #fff)",
            border: "none",
            borderRadius: 4,
            cursor: "pointer",
            transition: "background 0.2s",
          }}
          onMouseOver={e => (e.currentTarget.style.background = "var(--color-input-hover, --color-input)")}
          onMouseOut={e => (e.currentTarget.style.background = "var(--color-input, --color-input-hover)")}
          onClick={() => {
            navigator.clipboard.writeText(lines.join("\n"));
          }}
        >
          Copy
        </button>
      </div>
      <div
        style={{
          whiteSpace: "pre-wrap",
          background: "var(--color-background-transcribed)",
          color: "var(--color-text-transcribed)",
          padding: 10,
          borderRadius: 5,
        }}
      >
        {lines.map((line, i) => (
          <div key={i}>{line}</div>
        ))}
      </div>
    </div>
  );

}
