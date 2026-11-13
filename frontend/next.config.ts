import type { NextConfig } from "next";

// Static export: the Python server serves these files to the desktop window.
const config: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  devIndicators: false,
};

export default config;
