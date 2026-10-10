import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  serverExternalPackages: ["newrelic"],
  // React Compiler (stabilized at the top level in Next 16): Next applies it
  // via its SWC pipeline, so the only requirement beyond this flag is the
  // `babel-plugin-react-compiler` devDependency in package.json.
  reactCompiler: true,
};

export default nextConfig;