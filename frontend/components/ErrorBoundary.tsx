"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";
import { reportError } from "@/lib/api";

/** Shows what went wrong instead of a blank page, with a way to recover. */
export default class ErrorBoundary extends Component<{ children: ReactNode; resetKey: string; label?: string }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    reportError(`${this.props.label ? this.props.label + ": " : ""}${error.name}: ${error.message}`,
      `${error.stack ?? ""}\n${info.componentStack ?? ""}`);
  }

  componentDidUpdate(previous: { resetKey: string }) {
    if (previous.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="banner failed" style={{ maxWidth: 820 }}>
        <b>{this.props.label ? `${this.props.label} could not be displayed.` : "This page could not be displayed."}</b>
        <div style={{ marginTop: 6 }}>
          If you just updated OfficeFlow, close every OfficeFlow window and start it again. If the problem stays,
          send this message to your administrator:
        </div>
        <pre className="selectable" style={{ whiteSpace: "pre-wrap", fontSize: 12, marginTop: 10 }}>
          {error.name}: {error.message}
        </pre>
        <button className="btn" style={{ marginTop: 10 }} onClick={() => window.location.reload()}>Reload</button>
      </div>
    );
  }
}
