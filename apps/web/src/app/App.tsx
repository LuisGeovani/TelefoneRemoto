import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from "react";

import { DashboardPage, type Status } from "../features/dashboard/DashboardPage";
import { RemoteScreenPage } from "../features/screen/RemoteScreenPage";
import { api, ApiError } from "../lib/api";

type Session = { user_name: string; role: string; csrf_token: string };
type AuthState = { configured: boolean };
type AuthView = "loading" | "login" | "setup" | "recovery";
type View = "dashboard" | "screen";

const GENERIC_LOGIN_ERROR = "Credenciais inválidas.";

function viewFromLocation(): View {
  return window.location.hash === "#/screen" ? "screen" : "dashboard";
}

function authPath(path: "/" | "/login" | "/setup" | "/recovery") {
  window.history.replaceState(null, "", path);
}

function AuthPanel({ children }: { children: ReactNode }) {
  return <main className="login">
    <section className="panel">
      <p className="eyebrow">LOCAL-FIRST · TERMUX</p>
      <h1>S10 Control</h1>
      {children}
    </section>
  </main>;
}

function Login({ onAuthenticated, onRecovery }: {
  onAuthenticated: (session: Session) => void;
  onRecovery: () => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const session = await api<Session>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      onAuthenticated(session);
    } catch {
      setError(GENERIC_LOGIN_ERROR);
    } finally {
      setPassword("");
      setBusy(false);
    }
  };

  return <AuthPanel>
    <p>Entre com a única conta administrativa configurada neste S10.</p>
    <form onSubmit={submit}>
      <label>Username
        <input
          name="username"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          autoComplete="username"
          maxLength={64}
          autoFocus
          required
        />
      </label>
      <label>Password
        <input
          name="password"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="current-password"
          maxLength={256}
          required
        />
      </label>
      {error && <p className="error" role="alert">{error}</p>}
      <button type="submit" disabled={busy}>{busy ? "Entrando…" : "Entrar"}</button>
    </form>
    <button type="button" className="auth-link" onClick={onRecovery} disabled={busy}>Recuperar acesso</button>
  </AuthPanel>;
}

function Setup({ onAuthenticated }: { onAuthenticated: (session: Session) => void }) {
  const [token, setToken] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const session = await api<Session>("/api/v1/auth/setup", {
        method: "POST",
        body: JSON.stringify({ token, username, password, password_confirmation: confirmation }),
      });
      onAuthenticated(session);
    } catch (requestError) {
      const code = requestError instanceof ApiError ? requestError.code : "SETUP_FAILED";
      setError(code === "PASSWORD_MISMATCH"
        ? "As senhas não coincidem."
        : code === "INVALID_PASSWORD_POLICY"
          ? "Use uma senha com 12 a 256 caracteres."
          : "Não foi possível configurar a conta. Verifique o token local.");
    } finally {
      setPassword("");
      setConfirmation("");
      setBusy(false);
    }
  };

  return <AuthPanel>
    <p>Primeiro acesso: use o bootstrap token local para criar a única conta administrativa.</p>
    <form onSubmit={submit}>
      <label>Bootstrap token
        <input value={token} onChange={(event) => setToken(event.target.value)} autoComplete="one-time-code" required />
      </label>
      <label>Username
        <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" maxLength={64} required />
      </label>
      <label>Password
        <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" minLength={12} maxLength={256} required />
      </label>
      <label>Confirmar password
        <input type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="new-password" minLength={12} maxLength={256} required />
      </label>
      {error && <p className="error" role="alert">{error}</p>}
      <button type="submit" disabled={busy}>{busy ? "Configurando…" : "Criar conta administrativa"}</button>
    </form>
  </AuthPanel>;
}

function Recovery({ onAuthenticated, onCancel }: {
  onAuthenticated: (session: Session) => void;
  onCancel: () => void;
}) {
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const session = await api<Session>("/api/v1/auth/recovery", {
        method: "POST",
        body: JSON.stringify({ token, password, password_confirmation: confirmation }),
      });
      onAuthenticated(session);
    } catch (requestError) {
      const code = requestError instanceof ApiError ? requestError.code : "RECOVERY_FAILED";
      setError(code === "PASSWORD_MISMATCH"
        ? "As senhas não coincidem."
        : code === "INVALID_PASSWORD_POLICY"
          ? "Use uma senha com 12 a 256 caracteres."
          : "Recuperação recusada. Gere ou confira o bootstrap token no Termux.");
    } finally {
      setPassword("");
      setConfirmation("");
      setBusy(false);
    }
  };

  return <AuthPanel>
    <p>Recuperação local: gere um bootstrap token no Termux e defina uma nova senha.</p>
    <form onSubmit={submit}>
      <label>Bootstrap token
        <input value={token} onChange={(event) => setToken(event.target.value)} autoComplete="one-time-code" required />
      </label>
      <label>Nova password
        <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" minLength={12} maxLength={256} required />
      </label>
      <label>Confirmar password
        <input type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="new-password" minLength={12} maxLength={256} required />
      </label>
      {error && <p className="error" role="alert">{error}</p>}
      <button type="submit" disabled={busy}>{busy ? "Redefinindo…" : "Redefinir password"}</button>
    </form>
    <button type="button" className="auth-link" onClick={onCancel} disabled={busy}>Voltar ao login</button>
  </AuthPanel>;
}

export function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [authView, setAuthView] = useState<AuthView>("loading");
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [view, setView] = useState<View>(viewFromLocation);
  const [loggingOut, setLoggingOut] = useState(false);

  const showLogin = useCallback(() => {
    setSession(null);
    setStatus(null);
    setAuthView("login");
    authPath("/login");
  }, []);

  const authenticated = useCallback((next: Session) => {
    setSession(next);
    setAuthView("login");
    authPath("/");
  }, []);

  const refresh = useCallback(async () => {
    try {
      setStatus(await api<Status>("/api/v1/status"));
      setError("");
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 401) {
        showLogin();
      } else {
        setError("Não foi possível atualizar o estado local.");
      }
    }
  }, [showLogin]);

  const verify = useCallback(async () => {
    try {
      authenticated(await api<Session>("/api/v1/auth/session"));
    } catch {
      setSession(null);
      setStatus(null);
      try {
        const state = await api<AuthState>("/api/v1/auth/state");
        const recoveryRequested = state.configured && window.location.pathname === "/recovery";
        setAuthView(recoveryRequested ? "recovery" : state.configured ? "login" : "setup");
        authPath(recoveryRequested ? "/recovery" : state.configured ? "/login" : "/setup");
      } catch {
        setAuthView("login");
        setError("Não foi possível consultar a autenticação local.");
      }
    }
  }, [authenticated]);

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

  const logout = async () => {
    if (!session || loggingOut) return;
    setLoggingOut(true);
    try {
      await api("/api/v1/auth/logout", {
        method: "POST",
        headers: { "X-CSRF-Token": session.csrf_token },
      });
      showLogin();
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 401) showLogin();
      else setError("Não foi possível encerrar a sessão.");
    } finally {
      setLoggingOut(false);
    }
  };

  if (authView === "loading") return <AuthPanel><p>Verificando sessão local…</p></AuthPanel>;
  if (!session && authView === "setup") return <Setup onAuthenticated={authenticated} />;
  if (!session && authView === "recovery") return <Recovery onAuthenticated={authenticated} onCancel={showLogin} />;
  if (!session) return <Login onAuthenticated={authenticated} onRecovery={() => {
    setAuthView("recovery");
    authPath("/recovery");
  }} />;

  return <main className="app-shell">
    <header className="app-header">
      <div className="brand">
        <p className="eyebrow">S10 CONTROL SERVER</p>
        <h1>S10 Control</h1>
      </div>
      <nav aria-label="Navegação principal">
        <button type="button" className={view === "dashboard" ? "active" : ""} aria-current={view === "dashboard" ? "page" : undefined} onClick={() => navigate("dashboard")}>Dashboard</button>
        <button type="button" className={view === "screen" ? "active" : ""} aria-current={view === "screen" ? "page" : undefined} onClick={() => navigate("screen")}>Tela remota</button>
      </nav>
      <div className="identity">
        <span><span className="dot online" />{session.user_name}</span>
        <button type="button" className="logout-button" onClick={() => void logout()} disabled={loggingOut}>{loggingOut ? "Saindo…" : "Sair"}</button>
      </div>
    </header>

    {view === "dashboard"
      ? <DashboardPage status={status} error={error} />
      : <RemoteScreenPage role={session.role} csrfToken={session.csrf_token} dashboardAdb={status?.network.adb} onUnauthorized={showLogin} />}
  </main>;
}
