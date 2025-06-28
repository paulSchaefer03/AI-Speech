import { useEffect, useRef } from "react";

export default function AudioVisualizer({ isRecording }: { isRecording: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const dataArrayRef = useRef<Uint8Array | null>(null);
  const animationIdRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

    // Zusatz: Zustand zwischenspeichern, ob vorher aufgenommen wurde
  const hasRecordedRef = useRef<boolean>(false);

  // Marker-Funktion: Trennlinie am rechten Rand
  const drawSeparatorLine = () => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    ctx.strokeStyle = "#EF4444"; // Tailwind red-500 (für Kontrast)
    ctx.beginPath();
    ctx.moveTo(width - 1, 0);
    ctx.lineTo(width - 1, height);
    ctx.stroke();
  };


  useEffect(() => {
    if (!isRecording && hasRecordedRef.current) {
      drawSeparatorLine();
      hasRecordedRef.current = false;
    }
    if (!isRecording) {
      if (animationIdRef.current) {
        cancelAnimationFrame(animationIdRef.current);
      }
      if (audioContextRef.current) {
        audioContextRef.current.close();
        audioContextRef.current = null;
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }
      return;
    }

    const initVisualizer = async () => {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const audioContext = new AudioContext();
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 2048;

      const bufferLength = analyser.fftSize;
      const dataArray = new Uint8Array(bufferLength);

      source.connect(analyser);

      audioContextRef.current = audioContext;
      analyserRef.current = analyser;
      dataArrayRef.current = dataArray;

      const canvas = canvasRef.current;
      const canvasCtx = canvas?.getContext("2d");

      if (!canvas || !canvasCtx) return;

      hasRecordedRef.current = true;

      const draw = () => {
        if (!analyserRef.current || !dataArrayRef.current) return;

        analyserRef.current.getByteTimeDomainData(dataArrayRef.current);

        const height = canvas.height;
        const width = canvas.width;

        const midpoint = height / 2;
        const v = dataArrayRef.current[0] / 128.0;
        const sensitivity = 1.8;
        const y = (v - 1) * midpoint * sensitivity + midpoint;


        // shift canvas content 1px to the left
        const imageData = canvasCtx.getImageData(1, 0, width - 1, height);
        canvasCtx.putImageData(imageData, 0, 0);

        // draw new vertical line at right edge
        canvasCtx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue('--color-foreground') || "#60A5FA";
        canvasCtx.fillRect(width - 1, 0, 1, height); // clear current line
        canvasCtx.clearRect(width - 1, 0, 1, height); // reset before drawing

        canvasCtx.beginPath();
        canvasCtx.moveTo(width - 1, midpoint);
        canvasCtx.lineTo(width - 1, y);
        canvasCtx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue('--color-foreground') || "#60A5FA";
        canvasCtx.stroke();

        animationIdRef.current = requestAnimationFrame(draw);
      };

      draw();
    };

    initVisualizer();

    return () => {
      if (animationIdRef.current) cancelAnimationFrame(animationIdRef.current);
      if (audioContextRef.current) {
        audioContextRef.current.close();
        audioContextRef.current = null;
      }
      if (streamRef.current) streamRef.current.getTracks().forEach((track) => track.stop());
    };
  }, [isRecording]);

  return (
    <canvas
      ref={canvasRef}
      width={600}
      height={100}
      className="w-full rounded-lg mb-6 border"
      style={{
        background: "var(--color-background)",
        border: "1px solid var(--color-border)"
      }}
    />
  );
}
