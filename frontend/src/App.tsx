import { useEffect, useMemo, useState, type FormEvent } from "react";
import { AppFooter } from "./components/AppFooter";
import { AppHeader } from "./components/AppHeader";
import { InputArea } from "./components/InputArea";
import { ReturnArea } from "./components/ReturnArea";
import { IngestProgress } from "./components/IngestProgress";
import {
  AuthRequiredScreen,
  BootErrorScreen,
  LoadingScreen,
} from "./components/StartupScreens";
import { endpointConfigs } from "./config/endpoints";
import {
  TOKEN_COOKIE_NAME,
  clearTokenCookie,
  getCookie,
  setTokenCookie,
} from "./lib/auth";
import { isRecord } from "./lib/json";
import { buildRequest, endpointDefaults } from "./lib/request-builder";
import type {
  EndpointConfig,
  FormsState,
  LoadingState,
  RenderMode,
  ResponsesState,
} from "./types/api";

function App() {
  const [token, setToken] = useState<string>("");
  const [tokenInput, setTokenInput] = useState<string>("");
  const [forms, setForms] = useState<FormsState>(() =>
    endpointDefaults(endpointConfigs),
  );
  const [responses, setResponses] = useState<ResponsesState>({});
  const [loadingById, setLoadingById] = useState<LoadingState>({});
  const [renderMode, setRenderMode] = useState<RenderMode>("json");
  const [apiRequiresAuth, setApiRequiresAuth] = useState<boolean>(false);
  const [bootLoading, setBootLoading] = useState<boolean>(true);
  const [bootError, setBootError] = useState<string>("");
  const [showAuthPanel, setShowAuthPanel] = useState<boolean>(false);

  const [activeEndpointId, setActiveEndpointId] = useState<string>(() => {
    const hashId = window.location.hash.replace("#", "");
    if (endpointConfigs.some((entry) => entry.id === hashId)) {
      return hashId;
    }
    return endpointConfigs[0].id;
  });

  useEffect(() => {
    function syncHashToActiveEndpoint() {
      const hashId = window.location.hash.replace("#", "");
      if (endpointConfigs.some((entry) => entry.id === hashId)) {
        setActiveEndpointId(hashId);
      }
    }

    window.addEventListener("hashchange", syncHashToActiveEndpoint);
    return () =>
      window.removeEventListener("hashchange", syncHashToActiveEndpoint);
  }, []);

  useEffect(() => {
    async function bootstrapApiRequirements() {
      const existingToken = getCookie(TOKEN_COOKIE_NAME);
      if (existingToken) {
        setToken(existingToken);
        setTokenInput(existingToken);
      }

      try {
        const response = await fetch("/api", {
          method: "GET",
          headers: {
            Accept: "application/json",
          },
        });

        if (!response.ok) {
          throw new Error(`Startup request failed with ${response.status}`);
        }

        const payload = (await response.json()) as unknown;
        if (isRecord(payload)) {
          const hasAuthValue = payload.has_auth;
          setApiRequiresAuth(
            typeof hasAuthValue === "boolean" ? hasAuthValue : false,
          );
        } else {
          setApiRequiresAuth(false);
        }
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Unable to query /api.";
        setBootError(message);
      } finally {
        setBootLoading(false);
      }
    }

    bootstrapApiRequirements();
  }, []);

  const navItems = useMemo(
    () =>
      endpointConfigs.map((config) => ({ id: config.id, title: config.title })),
    [],
  );

  const activeConfig = useMemo(
    () =>
      endpointConfigs.find((entry) => entry.id === activeEndpointId) ??
      endpointConfigs[0],
    [activeEndpointId],
  );

  const activeResponse = responses[activeConfig.id];
  const activeLoading = Boolean(loadingById[activeConfig.id]);

  function updateField(endpointId: string, key: string, value: string): void {
    setForms((prev) => ({
      ...prev,
      [endpointId]: {
        ...prev[endpointId],
        [key]: value,
      },
    }));
  }

  function handleEndpointSelect(id: string): void {
    setActiveEndpointId(id);
  }

  function handleLogin(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const value = tokenInput.trim();
    if (!value) {
      return;
    }

    setTokenCookie(value);
    setToken(value);
    setShowAuthPanel(false);
  }

  function handleLogout(): void {
    clearTokenCookie();
    setToken("");
    setTokenInput("");
    setShowAuthPanel(false);
  }

  async function runEndpoint(config: EndpointConfig): Promise<void> {
    const values = forms[config.id] ?? {};

    setLoadingById((prev) => ({ ...prev, [config.id]: true }));

    try {
      const request = buildRequest(config, values);
      const headers: HeadersInit = {
        Accept: "application/json",
      };

      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }

      if (config.method !== "GET") {
        headers["Content-Type"] = "application/json";
      }

      const response = await fetch(request.url, {
        method: config.method,
        headers,
        body:
          config.method !== "GET" && request.body
            ? JSON.stringify(request.body)
            : undefined,
      });

      const text = await response.text();
      let parsed: unknown = text;
      if (text) {
        try {
          parsed = JSON.parse(text) as unknown;
        } catch {
          parsed = text;
        }
      }

      setResponses((prev) => ({
        ...prev,
        [config.id]: {
          ok: response.ok,
          status: response.status,
          url: request.url,
          response: parsed,
        },
      }));
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unknown client error";
      setResponses((prev) => ({
        ...prev,
        [config.id]: {
          ok: false,
          status: "client",
          url: config.path,
          response: { error: message },
        },
      }));
    } finally {
      setLoadingById((prev) => ({ ...prev, [config.id]: false }));
    }
  }

  function renderGrowContent() {
    if (bootLoading) {
      return <LoadingScreen />;
    }

    if (bootError) {
      return <BootErrorScreen message={bootError} />;
    }

    if (apiRequiresAuth && !token) {
      return (
        <AuthRequiredScreen
          tokenInput={tokenInput}
          onTokenInputChange={setTokenInput}
          onSubmit={handleLogin}
        />
      );
    }

    return (
      <>
        <AppHeader
          apiRequiresAuth={apiRequiresAuth}
          showAuthPanel={showAuthPanel}
          token={token}
          tokenInput={tokenInput}
          navItems={navItems}
          activeEndpointId={activeConfig.id}
          onEndpointSelect={handleEndpointSelect}
          onToggleAuthPanel={() => setShowAuthPanel((prev) => !prev)}
          onTokenInputChange={setTokenInput}
          onLogin={handleLogin}
          onLogout={handleLogout}
        />

        <main className="mx-auto grid w-full max-w-448 gap-5 px-4 py-6 lg:px-6">
          <IngestProgress
            token={token}
            onIngestCompleted={() => {
              if (
                activeConfig.id === "stats" ||
                activeConfig.id === "import-tasks"
              ) {
                void runEndpoint(activeConfig);
              }
            }}
          />

          <InputArea
            config={activeConfig}
            values={forms[activeConfig.id] ?? {}}
            isLoading={activeLoading}
            onFieldChange={(key, value) =>
              updateField(activeConfig.id, key, value)
            }
            onSubmit={() => runEndpoint(activeConfig)}
          />

          <ReturnArea
            renderMode={renderMode}
            onRenderModeChange={setRenderMode}
            response={activeResponse}
          />
        </main>
      </>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-zinc-950 text-zinc-100">
      <div className="grow">{renderGrowContent()}</div>
      <div className="shrink">
        <AppFooter />
      </div>
    </div>
  );
}

export default App;
