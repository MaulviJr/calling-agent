import { createServer } from "node:http";
import next from "next";
import httpProxy from "http-proxy";

const dev = !process.argv.includes("--production");
const port = Number(process.env.PORT || 8000);
const hostname = process.env.HOST || "127.0.0.1";
const target = process.env.BACKEND_URL || "http://127.0.0.1:8001";
const app = next({ dev, hostname, port, webpack: true });
const proxy = httpProxy.createProxyServer({ target, ws: true });

proxy.on("error", (_error, _request, response) => {
  if ("writeHead" in response && !response.headersSent) {
    response.writeHead(502, { "Content-Type": "application/json" });
    response.end(JSON.stringify({ detail: "Ava backend is unavailable." }));
  } else {
    response.destroy();
  }
});

await app.prepare();
const handle = app.getRequestHandler();
const handleUpgrade = app.getUpgradeHandler();

// A single public origin preserves the existing HttpOnly cookie, CSRF Origin
// checks and /api/voice protocol. Do not rewrite Cookie or Origin headers.
const server = createServer((request, response) => {
  const path = new URL(request.url, "http://localhost").pathname;
  if (path === "/api" || path.startsWith("/api/") || path === "/health") {
    proxy.web(request, response);
    return;
  }
  response.setHeader("X-Content-Type-Options", "nosniff");
  response.setHeader("Referrer-Policy", "no-referrer");
  response.setHeader("X-Frame-Options", "DENY");
  handle(request, response);
});

server.on("upgrade", (request, socket, head) => {
  const path = new URL(request.url, "http://localhost").pathname;
  if (path === "/api/voice") {
    proxy.ws(request, socket, head);
  } else {
    handleUpgrade(request, socket, head);
  }
});

server.listen(port, hostname, () => {
  console.log(`Ava frontend: http://localhost:${port} (backend: ${target})`);
});
