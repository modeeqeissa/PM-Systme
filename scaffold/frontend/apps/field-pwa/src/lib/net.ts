import { useEffect, useState } from "react";

/**
 * `navigator.onLine` + the online/offline events. This is a hint, not a
 * guarantee (it only knows about the network interface, not reachability), so
 * the sync path also treats a failed fetch as "offline". Used here just to
 * drive the UI banner and to kick a sync when connectivity returns.
 */
export function useOnline(): boolean {
  const [online, setOnline] = useState(() =>
    typeof navigator === "undefined" ? true : navigator.onLine,
  );
  useEffect(() => {
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => {
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
    };
  }, []);
  return online;
}
