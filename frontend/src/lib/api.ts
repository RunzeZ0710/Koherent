const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export type ClassCreated = {
  id: string;
  name: string;
  join_code: string;
  owner_token: string;
  created_at: string;
};

export type StudentSession = {
  student_id: string;
  class_id: string;
  display_name: string;
  session_token: string;
};

export type LectureRead = {
  id: string;
  class_id: string;
  title: string | null;
  started_at: string;
  ended_at: string | null;
};

export type LectureStatus = LectureRead & {
  my_notes_count: number;
  has_audio: boolean;
};

export type NoteRead = {
  id: string;
  lecture_id: string;
  student_id: string;
  content: string;
  client_timestamp_ms: number;
  created_at: string;
};

export const api = {
  createClass: (name: string) =>
    request<ClassCreated>("/classes", { method: "POST", body: JSON.stringify({ name }) }),

  joinClass: (joinCode: string, displayName: string) =>
    request<StudentSession>("/classes/join", {
      method: "POST",
      body: JSON.stringify({ join_code: joinCode, display_name: displayName }),
    }),

  me: () => request<StudentSession>("/me"),

  startLecture: (title: string | null) =>
    request<LectureRead>("/lectures", { method: "POST", body: JSON.stringify({ title }) }),

  getLecture: (id: string) => request<LectureStatus>(`/lectures/${id}`),

  postNote: (lectureId: string, content: string, clientTimestampMs: number) =>
    request<NoteRead>(`/lectures/${lectureId}/notes`, {
      method: "POST",
      body: JSON.stringify({ content, client_timestamp_ms: clientTimestampMs }),
    }),

  uploadAudio: async (lectureId: string, blob: Blob) => {
    const form = new FormData();
    form.append("file", blob, "lecture.webm");
    const res = await fetch(`${BASE}/lectures/${lectureId}/audio`, {
      method: "POST",
      credentials: "include",
      body: form,
    });
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
    return res.json();
  },
};
