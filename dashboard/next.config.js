/** @type {import("next").NextConfig} */
const nextConfig = {
  // better-sqlite3 is a native addon. Mark it external so Next does not try to
  // bundle the prebuilt .node binary into the server build (which would break it).
  serverExternalPackages: ["better-sqlite3"],
  // Allow the dev VM's network IP as a dev origin. Without this, Next 16's
  // cross-origin guard blocks the HMR WebSocket when the dashboard is browsed
  // from another host (operator PC -> http://10.20.99.55:3000), HMR retries
  // by force-reloading the page several times per second, and the /api/live
  // setInterval is torn down before its first 500 ms tick.
  allowedDevOrigins: ["10.20.99.55"],
};

module.exports = nextConfig;
