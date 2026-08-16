import type { AdbStatus } from "../screen/types";

export type Indicator = { state: string; reason?: string | null };
export type LanIndicator = Indicator & { addresses?: string[] };

export type Status = {
  server: { state: string };
  cpu: { logical_cores: number | null; load_average: number[] | null };
  ram: { total_bytes: number | null; available_bytes: number | null; used_bytes: number | null };
  storage: { total_bytes: number; used_bytes: number; free_bytes: number };
  network: {
    lan: LanIndicator;
    internet: Indicator;
    ssh: Indicator;
    adb: AdbStatus;
    remote_access: Indicator;
  };
  battery: { state: string; data?: { percentage?: number; status?: string }; reason?: string };
};

const bytes = (value: number | null | undefined) => value == null
  ? "Indisponível"
  : `${(value / 1024 ** 3).toFixed(1)} GB`;

function stateClass(state: string): string {
  if (state === "online" || state === "ready" || state === "available") return "online";
  if (state === "degraded" || state === "connecting" || state === "unauthorized" || state === "error") return "degraded";
  return "offline";
}

function IndicatorCard({ label, value }: { label: string; value: Indicator }) {
  return <div className="indicator">
    <span className={`dot ${stateClass(value.state)}`} />
    <div>
      <strong>{label}</strong>
      <small>{value.state}{value.reason ? ` · ${value.reason}` : ""}</small>
    </div>
  </div>;
}

export function DashboardPage({ status, error }: { status: Status | null; error: string }) {
  const net = status?.network;
  return <section className="dashboard-page" aria-labelledby="dashboard-title">
    <div className="section-heading">
      <div>
        <p className="eyebrow">LOCAL-FIRST · TERMUX</p>
        <h2 id="dashboard-title">Painel local</h2>
      </div>
    </div>
    {error && <p className="error">{error}</p>}
    <section className="indicators" aria-label="Estado dos serviços">
      <IndicatorCard label="Servidor" value={{ state: status?.server.state ?? "offline" }} />
      <IndicatorCard label="LAN" value={net?.lan ?? { state: "offline" }} />
      <IndicatorCard label="Internet" value={net?.internet ?? { state: "offline" }} />
      <IndicatorCard label="SSH" value={net?.ssh ?? { state: "offline" }} />
      <IndicatorCard label="ADB" value={net?.adb ?? { state: "unavailable" }} />
      <IndicatorCard label="Remote Access" value={net?.remote_access ?? { state: "offline" }} />
    </section>
    <section className="cards">
      <article>
        <span>Bateria</span>
        <strong>{status?.battery.state === "ready" ? `${status.battery.data?.percentage ?? "?"}%` : "Indisponível"}</strong>
        <small>{status?.battery.data?.status ?? status?.battery.reason ?? "Termux:API opcional"}</small>
      </article>
      <article>
        <span>CPU</span>
        <strong>{status?.cpu.logical_cores ?? "?"} núcleos</strong>
        <small>Load: {status?.cpu.load_average?.[0]?.toFixed(2) ?? "—"}</small>
      </article>
      <article>
        <span>RAM</span>
        <strong>{bytes(status?.ram.used_bytes)}</strong>
        <small>{bytes(status?.ram.available_bytes)} disponível</small>
      </article>
      <article>
        <span>Armazenamento</span>
        <strong>{bytes(status?.storage.free_bytes)}</strong>
        <small>{bytes(status?.storage.used_bytes)} usado</small>
      </article>
      <article className="wide">
        <span>Rede local</span>
        <strong>{net?.lan.addresses?.join(", ") || "Sem endereço privado visível"}</strong>
        <small>A Internet é opcional; sua ausência não deixa o servidor unhealthy.</small>
      </article>
    </section>
  </section>;
}
