import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = {
  children: ReactNode;
};

type State = {
  error: Error | null;
};

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Creator Interface crashed:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="app-crash-fallback" role="alert">
          <strong>DEUS esta indisponivel.</strong>
          <p>A interface encontrou um erro inesperado. Recarregue a pagina para reconectar.</p>
          <button type="button" onClick={() => window.location.reload()}>
            Recarregar
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
