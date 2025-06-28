import React from "react";

export default function ModelSelector({
  models,
  selected,
  onChange,
}: {
  models: string[];
  selected: string;
  onChange: (val: string) => void;
}) {
  return (
    <div className="flex flex-col gap-2 my-4">
      <label className="text-sm font-medium text-muted-foreground">
        🤖 Modellauswahl
      </label>
      <select
        value={selected}
        onChange={(e) => onChange(e.target.value)}
        style={{
          padding: "10px",
          borderRadius: "5px",
          border: "1px solid var(--color-border)",
          background: "var(--color-background-transcribed)",
          color: "var(--color-text-transcribed)",
          outline: "none",
        }}
      >
        {models.map((model) => (
          <option key={model} value={model}>
        {model}
          </option>
        ))}
      </select>
    </div>
  );
}
