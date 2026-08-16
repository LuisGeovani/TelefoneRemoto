import { type FormEvent, useCallback, useEffect, useState } from "react";

import { DashboardPage, type Status } from "../features/dashboard/DashboardPage";
import { RemoteScreenPage } from "../features/screen/RemoteScreenPage";
import { api, ApiError } from "../lib/api";

type Session = { user_name: string; role: string; csrf_token: string };
type View = "dashboard" | "screen";

function viewFromLocation(): View {
  return window.location.hash === "#/screen" ? "screen" : "dashboard";
}

function Login({ onAuthenticated }: { onAuthenticated: () => void }) {
  const [token, setToken] = useState("");
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      await api("/api/v1/auth/bootstrap/exchange", {
        method: "POST",
        body: JSON.stringify({ token }),
      });
      onAuthenticated();
    } catch {
      setError("Token inválido, expirado ou já utilizado.");
    }
  };

  return <main className="login">
    <section className="panel">
      <p className="eyebrow">LOCAL-FIRST · TERMUX</p>
      <h1>S10 Control</h1>
      <p>Use o token de bootstrap obtido localmente no Termux. Ele é de uso único e expira em 15 minutos.</p>
      <form onSubmit={submit}>
        <label>Token de bootstrap
          <input
            aria-label="Token de bootstrap"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            autoComplete="one-time-code"
            required
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit">Entrar no painel</button>
      </form>
    </section>
  </main>;
}

export function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [view, setView] = useState<View>(viewFromLocation);

  const expireSession = useCallback(() => {
    setSession(null);
    setStatus(null);
  }, []);

  const refresh = useCallback(async () => {
    try {
      setStatus(await api<Status>("/api/v1/status"));
      setError("");
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 401) {
        expireSession();
      } else {
        setError("Não foi possível atualizar o estado local.");
      }
    }
  }, [expireSession]);

  const verify = useCallback(async () => {
    try {
      setSession(await api<Session>("/api/v1/auth/session"));
    } catch {
      expireSession();
    }
  }, [expireSession]);

  useEffect(() => {
    void verify();
  }, [verify]);

  useEffect(() => {
    const changed = () => setView(viewFromLocation());
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);

  useEffect(() => {
    if (!session) return;
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5_000);
    return () => window.clearInterval(timer);
  }, [session, refresh]);

  const navigate = (next: View) => {
    window.location.hash = next === "screen" ? "#/screen" : "#/";
    setView(next);
  };

  if (!session) return <Login onAuthenticated={() => void verify()} />;

  return <main className="app-shell">
    <header className="app-header">
      <div className="brand">
        <p className="eyebrow">S10 CONTROL SERVER</p>
        <h1>S10 Control</h1>
      </div>
      <nav aria-label="Navegação principal">
        <button
          type="button"
          className={view === "dashboard" ? "active" : ""}
          aria-current={view === "dashboard" ? "page" : undefined}
          onClick={() => navigate("dashboard")}
        >Dashboard</button>
        <button
          type="button"
          className={view === "screen" ? "active" : ""}
          aria-current={view === "screen" ? "page" : undefined}
          onClick={() => navigate("screen")}
        >Tela remota</button>
      </nav>
      <div className="identity"><span className="dot online" />{session.user_name} · {session.role}</div>
    </header>

    {view === "dashboard"
      ? <DashboardPage status={status} error={error} />
      : <RemoteScreenPage
        role={session.role}
        csrfToken={session.csrf_token}
        dashboardAdb={status?.network.adb}
        onUnauthorized={expireSession}
      />}
  </main>;
}
