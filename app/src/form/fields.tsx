import { createContext, useContext, useId, useState, type ReactNode } from "react";
import type { Document } from "yaml";
import type { ValidationIssue } from "../types";
import { getIn, pathKey, type Path } from "./doc";

export interface FormApi {
  data: Record<string, unknown>;
  /** Set a value; `undefined` removes the key. */
  set: (path: Path, value: unknown) => void;
  /** Several document changes as one edit. */
  edit: (fn: (doc: Document) => void) => void;
  issues: ValidationIssue[];
}

export const FormContext = createContext<FormApi | null>(null);

export function useForm(): FormApi {
  const api = useContext(FormContext);
  if (!api) throw new Error("useForm outside FormContext");
  return api;
}

/** Errors reported exactly at `path`. */
function useIssues(path: Path): string[] {
  const { issues } = useForm();
  const key = pathKey(path);
  return issues.filter((i) => pathKey(i.path) === key).map((i) => i.msg);
}

interface FieldShellProps {
  label: string;
  unit?: string;
  hint?: string;
  errors: string[];
  wide?: boolean;
  children: (id: string) => ReactNode;
}

function FieldShell({ label, unit, hint, errors, wide, children }: FieldShellProps) {
  const id = useId();
  return (
    <div className={`field${wide ? " wide" : ""}${errors.length ? " invalid" : ""}`}>
      <label htmlFor={id}>{label}</label>
      <div className="control">
        {children(id)}
        {unit && <span className="unit">{unit}</span>}
      </div>
      {errors.map((e, i) => (
        <span key={i} className="field-error" role="alert">
          {e}
        </span>
      ))}
      {hint && !errors.length && <span className="field-hint">{hint}</span>}
    </div>
  );
}

interface NumberFieldProps {
  path: Path;
  label: string;
  unit?: string;
  hint?: string;
  step?: number;
  /** Empty input removes the key (for optional settings with engine defaults). */
  optional?: boolean;
  placeholder?: string;
}

export function NumberField({ path, label, unit, hint, step, optional, placeholder }: NumberFieldProps) {
  const { data, set } = useForm();
  const value = getIn(data, path);
  const external = typeof value === "number" ? String(value) : "";
  // While typing, show the raw text so intermediate input like "0." or "-"
  // survives; otherwise show the document's value.
  const [draft, setDraft] = useState<string | null>(null);
  const shown = draft ?? external;

  const errors = useIssues(path);
  const localError =
    shown.trim() !== "" && !Number.isFinite(Number(shown)) ? ["Enter a number"] : [];

  return (
    <FieldShell label={label} unit={unit} hint={hint} errors={[...localError, ...errors]}>
      {(id) => (
        <input
          id={id}
          type="text"
          inputMode="decimal"
          value={shown}
          step={step}
          placeholder={placeholder}
          onFocus={() => setDraft(external)}
          onBlur={() => setDraft(null)}
          onChange={(e) => {
            const text = e.target.value;
            setDraft(text);
            if (text.trim() === "") {
              if (optional) set(path, undefined);
              return;
            }
            const n = Number(text);
            if (Number.isFinite(n)) set(path, n);
          }}
        />
      )}
    </FieldShell>
  );
}

interface TextFieldProps {
  path: Path;
  label: string;
  hint?: string;
  wide?: boolean;
  mono?: boolean;
  onRename?: (from: string, to: string) => void;
}

export function TextField({ path, label, hint, wide, mono, onRename }: TextFieldProps) {
  const { data, set } = useForm();
  const value = getIn(data, path);
  const errors = useIssues(path);
  return (
    <FieldShell label={label} hint={hint} errors={errors} wide={wide}>
      {(id) => (
        <input
          id={id}
          type="text"
          className={mono ? "mono" : undefined}
          spellCheck={false}
          value={typeof value === "string" ? value : value == null ? "" : String(value)}
          onChange={(e) => {
            if (onRename && typeof value === "string") onRename(value, e.target.value);
            else set(path, e.target.value);
          }}
        />
      )}
    </FieldShell>
  );
}

interface SelectFieldProps {
  path: Path;
  label: string;
  options: { value: string; label: string }[];
  hint?: string;
}

export function SelectField({ path, label, options, hint }: SelectFieldProps) {
  const { data, set } = useForm();
  const value = getIn(data, path);
  const errors = useIssues(path);
  return (
    <FieldShell label={label} hint={hint} errors={errors}>
      {(id) => (
        <select id={id} value={typeof value === "string" ? value : ""} onChange={(e) => set(path, e.target.value)}>
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      )}
    </FieldShell>
  );
}

export function CheckboxField({
  path,
  label,
  hint,
  disabled,
}: {
  path: Path;
  label: string;
  hint?: string;
  disabled?: boolean;
}) {
  const { data, set } = useForm();
  const errors = useIssues(path);
  const id = useId();
  return (
    <div className={`field wide${errors.length ? " invalid" : ""}`}>
      <label htmlFor={id} className="checkbox-label">
        <input
          id={id}
          type="checkbox"
          checked={getIn(data, path) === true}
          disabled={disabled}
          onChange={(e) => set(path, e.target.checked)}
        />
        {label}
      </label>
      {errors.map((e, i) => (
        <span key={i} className="field-error" role="alert">
          {e}
        </span>
      ))}
      {hint && !errors.length && <span className="field-hint">{hint}</span>}
    </div>
  );
}

/** ISO-8601 UTC timestamp edited as date + time in UTC. */
export function DateTimeField({
  path,
  label,
  hint,
  optional,
}: {
  path: Path;
  label: string;
  hint?: string;
  optional?: boolean;
}) {
  const { data, set } = useForm();
  const value = getIn(data, path);
  const errors = useIssues(path);
  const iso = value instanceof Date ? value.toISOString() : typeof value === "string" ? value : "";
  // datetime-local wants "YYYY-MM-DDTHH:MM:SS" with no zone; we treat it as UTC.
  const local = iso ? new Date(iso).toISOString().slice(0, 19) : "";
  return (
    <FieldShell label={label} unit="UTC" hint={hint} errors={errors} wide>
      {(id) => (
        <input
          id={id}
          type="datetime-local"
          step={1}
          value={local}
          onChange={(e) => {
            if (!e.target.value) {
              if (optional) set(path, undefined);
              return;
            }
            const withSeconds = e.target.value.length === 16 ? `${e.target.value}:00` : e.target.value;
            set(path, `${withSeconds}Z`);
          }}
        />
      )}
    </FieldShell>
  );
}

/** A two-or-more way choice rendered as a segmented control. */
export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div className="field wide">
      <span className="label">{label}</span>
      <div className="segmented" role="radiogroup" aria-label={label}>
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={value === o.value}
            className={value === o.value ? "on" : undefined}
            onClick={() => onChange(o.value)}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function Section({ title, children, defaultOpen = true }: { title: ReactNode; children: ReactNode; defaultOpen?: boolean }) {
  return (
    <details className="form-section" open={defaultOpen}>
      <summary>{title}</summary>
      <div className="form-section-body">{children}</div>
    </details>
  );
}
