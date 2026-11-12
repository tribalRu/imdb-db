import type {
  EndpointConfig,
  EndpointField,
  EndpointFormValues,
  FieldValue,
  FormsState,
} from "../types/api";

function normalizeFieldValue(
  field: EndpointField,
  rawValue: string | undefined,
): FieldValue {
  const value = typeof rawValue === "string" ? rawValue.trim() : rawValue;

  if (field.type === "number") {
    if (value === undefined || value === "") {
      return undefined;
    }
    const parsed = Number(value);
    if (Number.isNaN(parsed)) {
      throw new Error(`Field "${field.label}" must be a number.`);
    }
    return parsed;
  }

  if (field.type === "list") {
    if (!value) {
      return undefined;
    }
    const items = value
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);
    return items.length > 0 ? items : undefined;
  }

  if (value === "") {
    return undefined;
  }

  return value;
}

export function endpointDefaults(
  endpointConfigs: EndpointConfig[],
): FormsState {
  const initial: FormsState = {};
  endpointConfigs.forEach((config) => {
    initial[config.id] = {};
    config.fields.forEach((field) => {
      initial[config.id][field.key] = field.defaultValue ?? "";
    });
  });
  return initial;
}

export function buildRequest(
  config: EndpointConfig,
  values: EndpointFormValues,
): { url: string; body?: Record<string, Exclude<FieldValue, undefined>> } {
  let path = config.path;
  const query = new URLSearchParams();
  let body: Record<string, Exclude<FieldValue, undefined>> | undefined;

  config.fields.forEach((field) => {
    const parsed = normalizeFieldValue(field, values[field.key]);

    if (field.in === "path") {
      const token = `:${field.key}`;
      if (parsed === undefined) {
        return;
      }
      path = path.replace(token, encodeURIComponent(String(parsed)));
      return;
    }

    if (field.in === "query") {
      if (parsed === undefined) {
        return;
      }
      if (Array.isArray(parsed)) {
        parsed.forEach((item) => query.append(field.key, String(item)));
      } else {
        query.append(field.key, String(parsed));
      }
      return;
    }

    if (parsed === undefined) {
      return;
    }

    if (!body) {
      body = {};
    }
    body[field.key] = parsed;
  });

  const missingRequired = config.fields
    .filter((field) => field.required)
    .some(
      (field) => normalizeFieldValue(field, values[field.key]) === undefined,
    );

  if (missingRequired) {
    throw new Error(
      "Please fill all required fields before sending the request.",
    );
  }

  if (path.includes(":")) {
    throw new Error("Path parameter is missing.");
  }

  const queryString = query.toString();
  return {
    url: queryString ? `${path}?${queryString}` : path,
    body,
  };
}
