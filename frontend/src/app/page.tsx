import Link from "next/link";

export default function HomePage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-6 p-8">
      <h1 className="text-4xl font-semibold">Koherent</h1>
      <p className="text-neutral-600">AI-native notetaking for lectures.</p>
      <div className="flex gap-4">
        <Link
          href="/create"
          className="px-4 py-2 rounded bg-black text-white hover:bg-neutral-800"
        >
          Create a class
        </Link>
        <Link
          href="/join"
          className="px-4 py-2 rounded border border-black hover:bg-neutral-100"
        >
          Join a class
        </Link>
      </div>
    </main>
  );
}
