import { FormEvent, useCallback, useEffect, useState } from "react";

type Status = {
  server: { state: string };
  cpu: { logical_cores: number | null; load_average: number[] | null };
  ram: { total_bytes: number | null; available_bytes: number | null; used_bytes: number | null };
  storage: { total_bytes: number; used_bytes: number; free_bytes: number };
  network: {
    lan: LanIndicator; internet: Indicator; ssh: Indicator; adb: Indicator; remote_access: Indicator;
  };
  battery: { state: string; data?: { percentage?: number; status?: string }; reason?: string };
};
type Indicator = { state: string; reason?: string | null };
type LanIndicator = Indicator & { addresses?: string[] };
type Session = { user_name: string; role: string; csrf_token: string };

const api = async <T,>(path: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(path, { credentials: "same-origin", ...init, headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) } });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json() as Promise<T>;
};

const bytes = (value: number | null | undefined) => value == null ? "Indisponível" : `${(value / 1024 ** 3).toFixed(1)} GB`;
const stateClass = (state: string) => state === "online" || state === "ready" ? "online" : state === "degraded" ? "degraded" : "offline";

function IndicatorCard({ label, value }: { label: string; value: Indicator }) {
  return <div className="indicator"><span className={`dot ${stateClass(value.state)}`} /><div><strong>{label}</strong><small>{value.state}{value.reason ? ` · ${value.reason}` : ""}</small></div></div>;
}

function Login({ onAuthenticated }: { onAuthenticated: () => void }) {
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError("");
    try { await api("/api/v1/auth/bootstrap/exchange", { method: "POST", body: JSON.stringify({ token }) }); onAuthenticated(); }
    catch { setError("Token inválido, expirado ou já utilizado."); }
  };
  return <main className="login"><section className="panel"><p className="eyebrow">LOCAL-FIRST · TERMUX</p><h1>S10 Control</h1><p>Use o token de bootstrap obtido localmente no Termux. Ele é de uso único e expira em 15 minutos.</p><form onSubmit={submit}><label>Token de bootstrap<input aria-label="Token de bootstrap" value={token} onChange={(event) => setToken(event.target.value)} autoComplete="one-time-code" required /></label>{error && <p className="error">{error}</p>}<button type="submit">Entrar no painel</button></form></section></main>;
}

export function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const refresh = useCallback(async () => { try { setStatus(await api<Status>("/api/v1/status")); setError(""); } catch { setError("Não foi possível atualizar o estado local."); } }, []);
  const verify = useCallback(async () => { try { setSession(await api<Session>("/api/v1/auth/session")); } catch { setSession(null); } }, []);
  useEffect(() => { void verify(); }, [verify]);
  useEffect(() => { if (!session) return; void refresh(); const timer = window.setInterval(() => void refresh(), 5000); return () => window.clearInterval(timer); }, [session, refresh]);
  if (!session) return <Login onAuthenticated={() => void verify()} />;
  const net = status?.network;
  return <main className="dashboard"><header><div><p className="eyebrow">S10 CONTROL SERVER</p><h1>Painel local</h1></div><div className="identity"><span className="dot online" />{session.user_name} · {session.role}</div></header>{error && <p className="error">{error}</p>}<section className="indicators"><IndicatorCard label="Servidor" value={{ state: status?.server.state ?? "offline" }} /><IndicatorCard label="LAN" value={net?.lan ?? { state: "offline" }} /><IndicatorCard label="Internet" value={net?.internet ?? { state: "offline" }} /><IndicatorCard label="SSH" value={net?.ssh ?? { state: "offline" }} /><IndicatorCard label="ADB" value={net?.adb ?? { state: "offline" }} /><IndicatorCard label="Remote Access" value={net?.remote_access ?? { state: "offline" }} /></section><section className="cards"><article><span>Bateria</span><strong>{status?.battery.state === "ready" ? `${status.battery.data?.percentage ?? "?"}%` : "Indisponível"}</strong><small>{status?.battery.data?.status ?? status?.battery.reason ?? "Termux:API opcional"}</small></article><article><span>CPU</span><strong>{status?.cpu.logical_cores ?? "?"} núcleos</strong><small>Load: {status?.cpu.load_average?.[0]?.toFixed(2) ?? "—"}</small></article><article><span>RAM</span><strong>{bytes(status?.ram.used_bytes)}</strong><small>{bytes(status?.ram.available_bytes)} disponível</small></article><article><span>Armazenamento</span><strong>{bytes(status?.storage.free_bytes)}</strong><small>{bytes(status?.storage.used_bytes)} usado</small></article><article className="wide"><span>Rede local</span><strong>{net?.lan.addresses?.join(", ") || "Sem endereço privado visível"}</strong><small>A Internet é opcional; sua ausência não deixa o servidor unhealthy.</small></article></section></main>;
}
