"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type StudentSession } from "@/lib/api";

export default function ClassHomePage() {
  const router = useRouter();
  const [session, setSession] = useState<StudentSession | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    api
      .me()
      .then(setSession)
      .catch(() => router.push("/join"));
  }, [router]);

  async function startLecture() {
    setStarting(true);
    setError(null);
    try {
      const lecture = await api.startLecture(null);
      router.push(`/lecture/${lecture.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStarting(false);
    }
  }

  if (!session) {
    return <main className="p-8">Loading…</main>;
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-6 p-8">
      <h1 className="text-2xl font-semibold">Welcome, {session.display_name}</h1>
      <p className="text-neutral-600">
        Ready when class begins. Press start when the lecture kicks off.
      </p>
      <button
        onClick={startLecture}
        disabled={starting}
        className="px-6 py-3 rounded bg-black text-white text-lg disabled:opacity-50"
      >
        {starting ? "Starting…" : "Start a new lecture"}
      </button>
      {error && <p className="text-red-600 text-sm">{error}</p>}
    </main>
  );
}
