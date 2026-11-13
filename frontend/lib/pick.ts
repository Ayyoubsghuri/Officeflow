// Choose files or folders: native dialog on the desktop, in-app browser otherwise.

import { bridge } from "./desktop";

export type PickMode = "files" | "folder" | "file";

export async function nativePick(mode: PickMode, extensions: string[], start = ""): Promise<string[] | null> {
  const native = bridge();
  if (!native) return null; // caller shows the in-app browser
  const result = mode === "folder" ? await native.open_folder(start) : await native.open_files(extensions, start);
  return mode === "file" ? result.slice(0, 1) : result;
}
