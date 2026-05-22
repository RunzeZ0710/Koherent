"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

const FLUSH_INTERVAL_MS = 5_000;

export function NoteEditor({ lectureId, startedAt }: { lectureId: string; startedAt: number }) {
  const [text, setText] = useState("");
  const [savedCount, setSavedCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const bufferRef = useRef<string>("");
  const bufferStartRef = useRef<number>(Date.now());

  useEffect(() => {
    const interval = setInterval(async () => {
      const buf = bufferRef.current;
      if (!buf.trim()) return;
      const ts = bufferStartRef.current - startedAt;
      bufferRef.current = "";
      bufferStartRef.current = Date.now();
      try {
        await api.postNote(lectureId, buf, Math.max(ts, 0));
        setSavedCount((c) => c + 1);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        // restore buffer so we retry on next tick
        bufferRef.current = buf + bufferRef.current;
      }
    }, FLUSH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [lectureId, startedAt]);

  function onChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const next = e.target.value;
    // Whatever's been added since the last flush goes into the buffer
    const added = next.slice(text.length);
    if (added) {
      if (!bufferRef.current) bufferStartRef.current = Date.now();
      bufferRef.current += added;
    }
    setText(next);
  }

  return (
    <div className="flex flex-col gap-2">
      <textarea
        value={text}
        onChange={onChange}
        placeholder="Type your notes…"
        className="w-full min-h-[400px] border border-neutral-300 rounded p-3 font-mono text-sm leading-relaxed"
      />
      <div className="flex items-center justify-between text-xs text-neutral-500">
        <span>{savedCount} batch{savedCount === 1 ? "" : "es"} saved</span>
        {error && <span className="text-red-600">save error: {error}</span>}
      </div>
    </div>
  );
}
