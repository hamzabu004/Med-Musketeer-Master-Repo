import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // The browser tests build sample and API mode side by side, each in its own directory.
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
