import { Component, type ErrorInfo, type ReactNode } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Unhandled UI error", error, info);
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="m-6 border border-orange-500/50 bg-panel p-6 text-zinc-200">
          <p className="text-sm uppercase tracking-wide text-orange-300">
            UI Error
          </p>
          <p className="mt-2 text-sm">{this.state.error.message}</p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-4 border border-zinc-600 px-4 py-2 text-sm text-zinc-200 transition hover:border-zinc-400"
          >
            Reload
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
