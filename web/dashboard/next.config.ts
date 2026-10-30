import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // The browser tests build sample and API mode side by side, each in its own directory.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // The container image (Dockerfile) runs the standalone server.
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
};

export default nextConfig;
