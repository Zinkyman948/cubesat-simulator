// Client for the simcore engine API.
//
// Inside the desktop app the Tauri shell starts the engine on a random
// port and hands us the URL and a per-launch token. In a plain browser
// (development, or a hosted demo) we talk to a separately started
// `simcore serve` at VITE_ENGINE_URL.

import type { ExampleSummary, SimulationResult, ValidationIssue } from "./types";

interface Engine {
  url: string;
  token: string | null;
}

interface TauriEngineInfo {
  port: number;
  token: string;
}

const isTauri = "__TAURI_INTERNALS__" in window;
const DEFAULT_URL = import.meta.env.VITE_ENGINE_URL ?? "http://127.0.0.1:8765";

let enginePromise: Promise<Engine> | null = null;

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function resolveEngine(): Promise<Engine> {
  if (!isTauri) return { url: DEFAULT_URL, token: null };
  const { invoke } = await import("@tauri-apps/api/core");
  // The engine takes a few seconds to unpack and start on first launch.
  for (let attempt = 0; attempt < 600; attempt++) {
    const info = await invoke<TauriEngineInfo | null>("engine_info");
    if (info) return { url: `http://127.0.0.1:${info.port}`, token: info.token };
    await sleep(100);
  }
  throw new Error("The simulation engine did not start within 60 seconds.");
}

function engine(): Promise<Engine> {
  enginePromise ??= resolveEngine();
  return enginePromise;
}

export class ScenarioError extends Error {
  constructor(public issues: ValidationIssue[]) {
    super("Scenario is invalid");
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { url, token } = await engine();
  const headers = new Headers(init.headers);
  if (token) headers.set("X-Simcore-Token", token);
  if (init.body) headers.set("Content-Type", "application/json");

  let response: Response;
  try {
    response = await fetch(url + path, { ...init, headers });
  } catch {
    throw new Error(`Cannot reach the simulation engine at ${url}.`);
  }
  if (response.status === 422) {
    const body = await response.json();
    throw new ScenarioError(body.errors ?? []);
  }
  if (!response.ok) throw new Error(`Engine error ${response.status}: ${await response.text()}`);
  return response.json() as Promise<T>;
}

export async function waitForEngine(): Promise<string> {
  for (let attempt = 0; ; attempt++) {
    try {
      const health = await request<{ version: string }>("/api/health");
      return health.version;
    } catch (e) {
      if (attempt >= 50) throw e;
      await sleep(200);
    }
  }
}

export const listExamples = () => request<ExampleSummary[]>("/api/examples");

export const getExample = (id: string) =>
  request<{ id: string; yaml: string }>(`/api/examples/${encodeURIComponent(id)}`);

export const simulate = (yaml: string) =>
  request<SimulationResult>("/api/simulate", { method: "POST", body: JSON.stringify({ yaml }) });
