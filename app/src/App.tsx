import { useCallback, useEffect, useRef, useState } from "react";
import { ScenarioError, getExample, listExamples, simulate, validate, waitForEngine } from "./api";
import Globe from "./components/Globe";
import PassCharts from "./components/PassCharts";
import PassTable from "./components/PassTable";
import ScenarioEditor from "./components/ScenarioEditor";
import Summary from "./components/Summary";
import { load, save } from "./storage";
import type { ExampleSummary, PassRef, SimulationResult, ValidationIssue } from "./types";

type EngineState = { status: "starting" } | { status: "ok"; version: string } | { status: "error"; message: string };

function firstPass(result: SimulationResult): PassRef | null {
  let best: PassRef | null = null;
  for (const [station, passes] of Object.entries(result.passes)) {
    passes.forEach((pass, index) => {
      if (!best || pass.aos < best.pass.aos) best = { station, index, pass };
    });
  }
  return best;
}

export default function App() {
  const [engine, setEngine] = useState<EngineState>({ status: "starting" });
  const [examples, setExamples] = useState<ExampleSummary[]>([]);
  const [exampleId, setExampleId] = useState("");
  const [yaml, setYaml] = useState("");
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [selected, setSelected] = useState<PassRef | null>(null);
  const [running, setRunning] = useState(false);
  const [issues, setIssues] = useState<ValidationIssue[]>([]);
  const [error, setError] = useState<string | null>(null);
  // The example's original text, to detect edits and to revert.
  const [original, setOriginal] = useState("");
  const exampleIdRef = useRef("");

  const run = useCallback(async (text: string) => {
    setRunning(true);
    setIssues([]);
    setError(null);
    try {
      const r = await simulate(text);
      setResult(r);
      setSelected(firstPass(r));
    } catch (e) {
      if (e instanceof ScenarioError) setIssues(e.issues);
      else setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }, []);

  // Each example keeps its own edited draft, so switching examples never loses work.
  const loadExample = useCallback(
    async (id: string) => {
      const ex = await getExample(id);
      exampleIdRef.current = id;
      setExampleId(id);
      save("example", id);
      setOriginal(ex.yaml);
      const text = load(`draft:${id}`) ?? ex.yaml;
      setYaml(text);
      await run(text);
    },
    [run],
  );

  const changeYaml = useCallback(
    (text: string) => {
      setYaml(text);
      save(`draft:${exampleIdRef.current}`, text === original ? null : text);
    },
    [original],
  );

  const revert = useCallback(() => {
    setYaml(original);
    save(`draft:${exampleIdRef.current}`, null);
    run(original);
  }, [original, run]);

  // Live validation while editing, debounced; stale responses are ignored.
  const validationSeq = useRef(0);
  useEffect(() => {
    if (engine.status !== "ok" || !yaml) return;
    const seq = ++validationSeq.current;
    const timer = setTimeout(async () => {
      try {
        const found = await validate(yaml);
        if (seq === validationSeq.current) setIssues(found);
      } catch {
        // Engine errors surface when running; live checks stay quiet.
      }
    }, 350);
    return () => clearTimeout(timer);
  }, [yaml, engine.status]);

  // Connect to the engine, then load and run the first example.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const version = await waitForEngine();
        if (cancelled) return;
        setEngine({ status: "ok", version });
        const list = await listExamples();
        if (cancelled) return;
        setExamples(list);
        const remembered = load("example");
        const initial =
          list.find((e) => e.id === remembered) ?? list.find((e) => e.id === "sso_3u_demo") ?? list[0];
        if (initial) await loadExample(initial.id);
      } catch (e) {
        if (!cancelled) setEngine({ status: "error", message: e instanceof Error ? e.message : String(e) });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadExample]);

  const engineLabel =
    engine.status === "ok"
      ? `Engine ${engine.version}`
      : engine.status === "starting"
        ? "Starting engine…"
        : engine.message;

  return (
    <div className="app">
      <header className="topbar">
        <h1>CubeSat Simulator</h1>
        {result && <span className="scenario-name">{result.scenario.name}</span>}
        <span className={`engine-status ${engine.status}`} role="status">
          <span className="dot" />
          {engineLabel}
        </span>
      </header>

      <aside className="sidebar">
        <ScenarioEditor
          examples={examples}
          exampleId={exampleId}
          onExampleChange={loadExample}
          yaml={yaml}
          onYamlChange={changeYaml}
          edited={yaml !== original}
          onRevert={revert}
          onRun={() => run(yaml)}
          running={running}
          disabled={engine.status !== "ok"}
          issues={issues}
          error={error}
        />
        {result && <Summary result={result} />}
      </aside>

      <main className="main">
        <Globe result={result} selected={selected} />
        <section className="bottom">
          {result ? (
            <>
              <PassTable result={result} selected={selected} onSelect={setSelected} />
              <PassCharts result={result} selected={selected} />
            </>
          ) : (
            <p className="empty">{running ? "Running simulation…" : "Run a scenario to see passes."}</p>
          )}
        </section>
      </main>
    </div>
  );
}
