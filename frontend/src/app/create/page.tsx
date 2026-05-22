"use client";

import { useState } from "react";
import { api, type ClassCreated } from "@/lib/api";

export default function CreateClassPage() {
  const [name, setName] = useState("");
  const [klass, setKlass] = useState<ClassCreated | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      setKlass(await api.createClass(name));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (klass) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center gap-6 p-8">
        <h1 className="text-2xl font-semibold">Class created: {klass.name}</h1>
        <p className="text-neutral-600">Share this join code with your students:</p>
        <div className="text-5xl font-mono tracking-widest border-2 border-black rounded px-6 py-4">
          {klass.join_code}
        </div>
        <p className="text-xs text-neutral-500 max-w-md text-center">
          Keep your owner token safe — you&apos;ll need it for the professor dashboard in a future
          version: <code className="break-all">{klass.owner_token}</code>
        </p>
      </main>
    );
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-6 p-8">
      <h1 className="text-2xl font-semibold">Create a class</h1>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3 w-full max-w-sm">
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Econ 101"
          required
          className="border border-neutral-300 rounded px-3 py-2"
        />
        <button
          type="submit"
          disabled={submitting || !name}
          className="px-4 py-2 rounded bg-black text-white disabled:opacity-50"
        >
          {submitting ? "Creating…" : "Create class"}
        </button>
        {error && <p className="text-red-600 text-sm">{error}</p>}
      </form>
    </main>
  );
}
