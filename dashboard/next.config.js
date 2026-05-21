/** @type {import("next").NextConfig} */
const nextConfig = {
  // better-sqlite3 is a native addon. Mark it external so Next does not try to
  // bundle the prebuilt .node binary into the server build (which would break it).
  serverExternalPackages: ["better-sqlite3"],
};

module.exports = nextConfig;
