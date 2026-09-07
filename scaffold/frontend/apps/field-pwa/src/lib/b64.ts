/**
 * Evidence file bytes are persisted to IndexedDB as a base64 STRING, not an
 * ArrayBuffer or Blob.
 *
 * Why: IndexedDB Blob/ArrayBuffer support has historically been buggy on some
 * WebView / older Safari builds (and is flaky under our jsdom test env),
 * whereas a string round-trips through every implementation. The cost is a
 * ~33% size inflation in the outbox plus an encode/decode pass — acceptable
 * for field photos and PDFs (a few MB). A video-sized capture would need a
 * different approach (streamed upload / File System Access handle) — flagged
 * for a later slice.
 */
export function bytesToBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let s = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    s += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(s);
}

export function base64ToArrayBuffer(b64: string): ArrayBuffer {
  const s = atob(b64);
  const buf = new ArrayBuffer(s.length);
  const view = new Uint8Array(buf);
  for (let i = 0; i < s.length; i++) view[i] = s.charCodeAt(i);
  return buf;
}
