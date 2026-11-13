// Access to the native desktop window (pywebview bridge). Every function has a
// browser fallback so the interface also works in a normal browser tab.

import { api } from "./api";

interface Bridge {
  minimize(): Promise<void>;
  toggle_maximize(): Promise<boolean>;
  is_maximized(): Promise<boolean>;
  close(): Promise<void>;
  geometry(): Promise<{ x: number; y: number; width: number; height: number }>;
  set_geometry(x: number, y: number, width: number, height: number): Promise<void>;
  open_files(extensions: string[], directory: string): Promise<string[]>;
  open_folder(directory: string): Promise<string[]>;
  open_path(path: string): Promise<void>;
}

declare global {
  interface Window {
    pywebview?: { api: Bridge };
  }
}

export function bridge(): Bridge | null {
  if (typeof window === "undefined") return null;
  const candidate = window.pywebview?.api;
  return candidate && typeof candidate.minimize === "function" ? candidate : null;
}

/** Resolves once the bridge is injected (desktop) or after a short wait (browser). */
export function whenBridgeReady(): Promise<Bridge | null> {
  return new Promise((resolve) => {
    if (bridge()) return resolve(bridge());
    const done = () => resolve(bridge());
    window.addEventListener("pywebviewready", done, { once: true });
    setTimeout(done, 1500);
  });
}

export async function openPath(path: string): Promise<void> {
  const native = bridge();
  if (native) return native.open_path(path);
  await api("POST", "/api/open", { path });
}
