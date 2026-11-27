import { Component, type ErrorInfo, type ReactNode } from "react";

/** Last-resort boundary: a render crash shows a recoverable message instead of a blank page. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  override state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ui]", error, info.componentStack);
  }

  override render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-3 p-6 text-center">
        <h1 className="text-lg font-semibold">Something went wrong</h1>
        <p className="text-sm text-muted-foreground">The page hit an unexpected error. Your saved data is safe. Reload to continue; if it keeps happening, tell your administrator.</p>
        <div className="flex gap-2">
          <button className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground" onClick={() => window.location.reload()}>Reload</button>
          <button className="rounded-md border px-3 py-1.5 text-sm" onClick={() => this.setState({ error: null })}>Try again</button>
        </div>
      </div>
    );
  }
}
