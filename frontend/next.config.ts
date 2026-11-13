import type { NextConfig } from "next";
import pkg from "./package.json";

// Static export: the Python server serves these files to the desktop window.
const config: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  devIndicators: false,
  env: { NEXT_PUBLIC_UI_VERSION: pkg.version },
};

export default config;
