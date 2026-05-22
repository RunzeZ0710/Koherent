"use client";

import { use, useEffect, useState } from "react";
import { api, type LectureStatus } from "@/lib/api";
import { NoteEditor } from "@/components/NoteEditor";
import { AudioRecorder } from "@/components/AudioRecorder";

export default function LecturePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [status, setStatus] = useState<LectureStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getLecture(id).then(setStatus).catch((err) => setError(String(err)));
  }, [id]);

  if (error) return <main className="p-8 text-red-600">Error: {error}</main>;
  if (!status) return <main className="p-8">Loading…</main>;

  const startedAtMs = new Date(status.started_at).getTime();

  return (
    <main className="max-w-3xl mx-auto p-6 flex flex-col gap-6">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{status.title ?? "Lecture in progress"}</h1>
        <span className="text-xs text-neutral-500 font-mono">{status.id.slice(0, 8)}</span>
      </header>
      <AudioRecorder lectureId={id} />
      <NoteEditor lectureId={id} startedAt={startedAtMs} />
    </main>
  );
}
