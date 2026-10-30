import { Component, type ReactNode } from "react";

// Shows the error instead of a blank page when a screen fails to render.
export default class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error) {
    console.error("Render error:", error);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="card" style={{ margin: 24 }}>
        <h2>This screen failed to load</h2>
        <p className="small">Error: <span className="mono">{this.state.error.message}</span></p>
        <p className="small muted">Path: {window.location.pathname}</p>
        <button className="btn" onClick={() => { this.setState({ error: null }); window.location.reload(); }}>Reload</button>
      </div>
    );
  }
}
