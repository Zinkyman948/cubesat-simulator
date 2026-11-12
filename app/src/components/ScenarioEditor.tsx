import { useState } from "react";
import ScenarioForm from "../form/ScenarioForm";
import { load, save } from "../storage";
import type { ExampleSummary, ValidationIssue } from "../types";

type Tab = "form" | "yaml";

interface Props {
  examples: ExampleSummary[];
  exampleId: string;
  onExampleChange: (id: string) => void;
  yaml: string;
  onYamlChange: (text: string) => void;
  edited: boolean;
  onRevert: () => void;
  onRun: () => void;
  running: boolean;
  disabled: boolean;
  issues: ValidationIssue[];
  error: string | null;
}

export default function ScenarioEditor(props: Props) {
  const { examples, exampleId, onExampleChange, yaml, onYamlChange, onRun, running, disabled, issues } = props;
  const [tab, setTab] = useState<Tab>(() => (load("editor-tab") === "yaml" ? "yaml" : "form"));
  const chooseTab = (t: Tab) => {
    setTab(t);
    save("editor-tab", t);
  };

  return (
    <div className="editor-panel">
      <div className="section">
        <h2>Scenario</h2>
        <div className="row">
          <select
            value={exampleId}
            onChange={(e) => onExampleChange(e.target.value)}
            disabled={disabled}
            aria-label="Example scenario"
          >
            {examples.map((ex) => (
              <option key={ex.id} value={ex.id}>
                {ex.name}
              </option>
            ))}
          </select>
          <button className="primary" onClick={onRun} disabled={disabled || running} title="Run (Ctrl+Enter)">
            {running ? "Running…" : "Run"}
          </button>
        </div>
        {props.edited && (
          <div className="row edited-row">
            <span className="hint">Edited · saved automatically</span>
            <button type="button" className="link-button" onClick={props.onRevert}>
              Revert to example
            </button>
          </div>
        )}
      </div>

      <div className="tabs" role="tablist">
        {(["form", "yaml"] as Tab[]).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            className={tab === t ? "on" : undefined}
            onClick={() => chooseTab(t)}
          >
            {t === "form" ? "Form" : "YAML"}
          </button>
        ))}
        {issues.length > 0 && (
          <span className="issue-count" role="status">
            {issues.length} problem{issues.length > 1 ? "s" : ""}
          </span>
        )}
      </div>

      <div
        className="editor-body"
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            onRun();
          }
        }}
      >
        {props.error && (
          <ul className="errors">
            <li>{props.error}</li>
          </ul>
        )}
        {tab === "form" ? (
          <ScenarioForm yaml={yaml} onChange={onYamlChange} issues={issues} />
        ) : (
          <div className="yaml-editor">
            <textarea
              value={yaml}
              spellCheck={false}
              onChange={(e) => onYamlChange(e.target.value)}
              aria-label="Scenario YAML"
            />
            {issues.length > 0 && (
              <ul className="errors">
                {issues.map((issue, i) => (
                  <li key={i}>
                    <span className="loc">{issue.loc}</span>
                    <span>{issue.msg}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
