"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";
import { LectureRecorder, type RecorderState } from "@/lib/recorder";

export function AudioRecorder({ lectureId }: { lectureId: string }) {
  const recorderRef = useRef<LectureRecorder | null>(null);
  const [state, setState] = useState<RecorderState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [uploadedSize, setUploadedSize] = useState<number | null>(null);

  async function handleStart() {
    setError(null);
    try {
      const r = new LectureRecorder();
      await r.start();
      recorderRef.current = r;
      setState("recording");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleStop() {
    if (!recorderRef.current) return;
    setState("stopping");
    try {
      const blob = await recorderRef.current.stop();
      await api.uploadAudio(lectureId, blob);
      setUploadedSize(blob.size);
      setState("idle");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setState("idle");
    } finally {
      recorderRef.current = null;
    }
  }

  return (
    <div className="border border-neutral-300 rounded p-4 flex flex-col gap-3">
      <div className="flex items-center gap-3">
        {state === "idle" && (
          <button
            onClick={handleStart}
            className="px-4 py-2 rounded bg-red-600 text-white hover:bg-red-700"
          >
            Record lecture
          </button>
        )}
        {state === "recording" && (
          <>
            <span className="inline-block w-3 h-3 rounded-full bg-red-600 animate-pulse" />
            <span className="text-sm font-medium">Recording…</span>
            <button
              onClick={handleStop}
              className="ml-auto px-4 py-2 rounded bg-black text-white hover:bg-neutral-800"
            >
              Stop & upload
            </button>
          </>
        )}
        {state === "stopping" && <span className="text-sm">Uploading…</span>}
      </div>
      {uploadedSize !== null && (
        <p className="text-xs text-neutral-500">
          Uploaded {(uploadedSize / 1024).toFixed(1)} KB.
        </p>
      )}
      {error && <p className="text-red-600 text-xs">{error}</p>}
    </div>
  );
}
