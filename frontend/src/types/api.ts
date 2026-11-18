export type HttpMethod = "GET" | "POST";
export type FieldLocation = "path" | "query" | "body";
export type FieldType = "text" | "number" | "list";
export type FieldValue = string | number | string[] | undefined;
export type RenderMode = "json" | "rendered";

export interface EndpointField {
  key: string;
  label: string;
  in: FieldLocation;
  type: FieldType;
  required?: boolean;
  defaultValue?: string;
  placeholder?: string;
}

export interface EndpointConfig {
  id: string;
  title: string;
  method: HttpMethod;
  path: string;
  description: string;
  fields: EndpointField[];
}

export type EndpointFormValues = Record<string, string>;
export type FormsState = Record<string, EndpointFormValues>;

export interface EndpointResponse {
  ok: boolean;
  status: number | "client";
  url: string;
  response: unknown;
}

export type ResponsesState = Record<string, EndpointResponse>;
export type LoadingState = Record<string, boolean>;

export interface IngestProgressItem {
  name: string;
  status: string;
  duration?: number;
  error?: string;
}

export interface IngestProgressData {
  is_running: boolean;
  started_at: number | null;
  finished_at: number | null;
  elapsed_seconds: number;
  total_count: number;
  completed_count: number;
  percent: number;
  active_datasets: string[];
  items: IngestProgressItem[];
}
