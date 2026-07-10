import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async redirects() {
    return [
      {
        source: "/ask",
        destination: "/",
        permanent: true,
      },
    ];
  },
};

export default nextConfig;
