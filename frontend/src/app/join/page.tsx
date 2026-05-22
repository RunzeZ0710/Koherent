"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function JoinClassPage() {
  const router = useRouter();
  const [joinCode, setJoinCode] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.joinClass(joinCode.toUpperCase(), displayName);
      router.push("/class");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-6 p-8">
      <h1 className="text-2xl font-semibold">Join a class</h1>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3 w-full max-w-sm">
        <input
          type="text"
          value={joinCode}
          onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
          placeholder="Join code (e.g. ABC123)"
          required
          maxLength={6}
          className="border border-neutral-300 rounded px-3 py-2 font-mono tracking-widest text-center"
        />
        <input
          type="text"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="Your name"
          required
          className="border border-neutral-300 rounded px-3 py-2"
        />
        <button
          type="submit"
          disabled={submitting || !joinCode || !displayName}
          className="px-4 py-2 rounded bg-black text-white disabled:opacity-50"
        >
          {submitting ? "Joining…" : "Join class"}
        </button>
        {error && <p className="text-red-600 text-sm">{error}</p>}
      </form>
    </main>
  );
}
