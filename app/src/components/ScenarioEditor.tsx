import type { ExampleSummary, ValidationIssue } from "../types";

interface Props {
  examples: ExampleSummary[];
  exampleId: string;
  onExampleChange: (id: string) => void;
  yaml: string;
  onYamlChange: (text: string) => void;
  onRun: () => void;
  running: boolean;
  disabled: boolean;
  issues: ValidationIssue[];
  error: string | null;
}

export default function ScenarioEditor(props: Props) {
  const { examples, exampleId, onExampleChange, yaml, onYamlChange, onRun, running, disabled } = props;
  return (
    <>
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
          <button className="primary" onClick={onRun} disabled={disabled || running}>
            {running ? "Running…" : "Run"}
          </button>
        </div>
      </div>
      <div className="editor">
        <textarea
          value={yaml}
          spellCheck={false}
          onChange={(e) => onYamlChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              onRun();
            }
          }}
          aria-label="Scenario YAML"
        />
        <span className="hint">Edit the YAML and press Run (Ctrl+Enter).</span>
        {props.error && (
          <ul className="errors">
            <li>{props.error}</li>
          </ul>
        )}
        {props.issues.length > 0 && (
          <ul className="errors">
            {props.issues.map((issue, i) => (
              <li key={i}>
                <span className="loc">{issue.loc}</span>
                <span>{issue.msg}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}
