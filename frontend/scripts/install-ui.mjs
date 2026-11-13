// Copy the static export into the Python package, where the local server serves it.
import { cpSync, existsSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const source = join(root, "out");
const target = join(root, "..", "officeflow", "web");
if (!existsSync(join(source, "index.html"))) {
  console.error("Build output not found in", source);
  process.exit(1);
}
rmSync(target, { recursive: true, force: true });
cpSync(source, target, { recursive: true });
console.log("Interface installed to", target);
