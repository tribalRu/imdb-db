import type { EndpointConfig, EndpointFormValues } from "../types/api";

interface InputAreaProps {
  config: EndpointConfig;
  values: EndpointFormValues;
  isLoading: boolean;
  onFieldChange: (key: string, value: string) => void;
  onSubmit: () => void;
}

export function InputArea({
  config,
  values,
  isLoading,
  onFieldChange,
  onSubmit,
}: InputAreaProps) {
  return (
    <section
      id={config.id}
      className="border border-zinc-800 bg-panel p-4 shadow-flat"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-zinc-100">
            {config.title}
          </h2>
          <p className="text-sm text-zinc-400">{config.description}</p>
          <code className="mt-2 block text-xs text-zinc-500">
            {config.method} {config.path}
          </code>
        </div>
        <button
          type="button"
          onClick={onSubmit}
          disabled={isLoading}
          className="border border-amber-500 bg-amber-500/10 px-4 py-2 text-xs font-medium uppercase tracking-wide text-amber-300 transition hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isLoading ? "Loading..." : "Send Request"}
        </button>
      </div>

      {config.fields.length > 0 ? (
        <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          {config.fields.map((field) => (
            <label key={field.key} className="grid gap-1 text-sm text-zinc-300">
              <span>{field.label}</span>
              <input
                value={values[field.key] ?? ""}
                onChange={(event) =>
                  onFieldChange(field.key, event.target.value)
                }
                placeholder={field.placeholder ?? ""}
                type={field.type === "number" ? "number" : "text"}
                step={field.type === "number" ? "any" : undefined}
                inputMode={field.type === "number" ? "decimal" : undefined}
                className="w-full border border-zinc-700 bg-panelSoft px-3 py-3 text-zinc-100 outline-none transition focus:border-amber-500"
              />
            </label>
          ))}
        </div>
      ) : (
        <p className="mt-4 text-sm text-zinc-500">
          This endpoint has no input parameters.
        </p>
      )}
    </section>
  );
}
