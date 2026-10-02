import type { NextConfig } from "next";

const config: NextConfig = {
  // The repository also has a root package.json. This is the application root.
  outputFileTracingRoot: process.cwd(),
  poweredByHeader: false,
};

export default config;
