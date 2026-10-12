import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Microphone recording, with the states the interface actually needs to show.
 *
 * The old version had two states and the learner could not tell a permission
 * prompt from a stalled upload. These five are each visually distinct in the
 * record control:
 *
 *   idle -> requesting -> recording -> (caller takes over: processing)
 *                      \-> denied | unsupported
 *
 * Recording happens in the browser, not the server: MediaRecorder hands over
 * webm/opus and the backend converts it with ffmpeg. That keeps the microphone
 * out of the Python process entirely.
 */

export type RecorderState = "idle" | "requesting" | "recording" | "denied" | "unsupported";

const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/mp4",
];

function pickMimeType(): string | null {
  if (typeof MediaRecorder === "undefined") return null;
  return MIME_CANDIDATES.find((type) => MediaRecorder.isTypeSupported(type)) ?? "";
}

export function useRecorder() {
  const [state, setState] = useState<RecorderState>("idle");
  const [elapsed, setElapsed] = useState(0);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const tickRef = useRef<number | null>(null);

  const cleanup = useCallback(() => {
    if (tickRef.current !== null) {
      window.clearInterval(tickRef.current);
      tickRef.current = null;
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    recorderRef.current = null;
  }, []);

  // A recording left running when the learner navigates away would hold the
  // microphone open and keep the browser's indicator lit.
  useEffect(() => cleanup, [cleanup]);

  const start = useCallback(async (): Promise<boolean> => {
    const mimeType = pickMimeType();
    if (mimeType === null) {
      setState("unsupported");
      return false;
    }

    setState("requesting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      streamRef.current = stream;

      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.start();
      recorderRef.current = recorder;

      setElapsed(0);
      const startedAt = performance.now();
      tickRef.current = window.setInterval(() => {
        setElapsed((performance.now() - startedAt) / 1000);
      }, 100);

      setState("recording");
      return true;
    } catch {
      cleanup();
      setState("denied");
      return false;
    }
  }, [cleanup]);

  const stop = useCallback(async (): Promise<Blob | null> => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") {
      cleanup();
      setState("idle");
      return null;
    }
    const blob = await new Promise<Blob>((resolve) => {
      recorder.onstop = () =>
        resolve(new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" }));
      recorder.stop();
    });
    cleanup();
    setState("idle");
    return blob;
  }, [cleanup]);

  const reset = useCallback(() => {
    cleanup();
    setState("idle");
    setElapsed(0);
  }, [cleanup]);

  return {
    state,
    elapsed,
    recording: state === "recording",
    start,
    stop,
    reset,
  };
}
