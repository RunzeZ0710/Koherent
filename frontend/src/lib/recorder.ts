export type RecorderState = "idle" | "recording" | "stopping";

export class LectureRecorder {
  private mediaRecorder: MediaRecorder | null = null;
  private chunks: BlobPart[] = [];
  private stream: MediaStream | null = null;

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mr = new MediaRecorder(this.stream, { mimeType: "audio/webm" });
    this.chunks = [];
    mr.ondataavailable = (e) => {
      if (e.data.size > 0) this.chunks.push(e.data);
    };
    mr.start(1000); // emit a chunk per second
    this.mediaRecorder = mr;
  }

  stop(): Promise<Blob> {
    return new Promise((resolve, reject) => {
      const mr = this.mediaRecorder;
      if (!mr) {
        reject(new Error("Recorder not started"));
        return;
      }
      mr.onstop = () => {
        const blob = new Blob(this.chunks, { type: "audio/webm" });
        this.stream?.getTracks().forEach((t) => t.stop());
        this.stream = null;
        this.mediaRecorder = null;
        resolve(blob);
      };
      mr.stop();
    });
  }
}
