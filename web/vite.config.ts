/// <reference types="vitest/config" />
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { resolveMock } from "./src/api/mock.ts";

const here = dirname(fileURLToPath(import.meta.url));

// The lead's API samples (python -m rmprep.api.samples).
const SAMPLES = resolve(here, "../tests/contracts/fixtures/api");

function loadSample(name: string): unknown | undefined {
  const file = resolve(SAMPLES, `${name}.json`);
  return existsSync(file) ? JSON.parse(readFileSync(file, "utf8")) : undefined;
}

/** `npm run dev:mock`: answer /api/* from the sample files, no Python needed. */
function mockApi(): Plugin {
  return {
    name: "rmprep-mock-api",
    configureServer(server) {
      server.middlewares.use("/api", (req, res) => {
        let raw = "";
        req.on("data", (chunk) => (raw += chunk));
        req.on("end", () => {
          const body = raw ? JSON.parse(raw) : undefined;
          const answer = resolveMock(req.method ?? "GET", "/api" + (req.url ?? ""), body, loadSample);
          res.statusCode = answer.status;
          res.setHeader("Content-Type", answer.type ?? "application/json; charset=utf-8");
          res.end(typeof answer.body === "string" ? answer.body : JSON.stringify(answer.body));
        });
      });
    },
  };
}

export default defineConfig(({ mode }) => ({
  plugins: [react(), ...(mode === "mock" ? [mockApi()] : [])],
  server: {
    proxy: mode === "mock" ? undefined : { "/api": "http://127.0.0.1:8600" },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
}));
