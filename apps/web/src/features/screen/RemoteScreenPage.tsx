import {
  type CSSProperties,
  type FormEvent,
  type PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { api, ApiError } from "../../lib/api";
import { isKnownRotation, pointInContainedFrame, type NormalizedPoint } from "./geometry";
import type { AdbStatus, AndroidKeyAction, FrameReference, ScreenFrame } from "./types";
import { useScreenStream } from "./useScreenStream";

type Props = {
  role: string;
  csrfToken: string;
  dashboardAdb?: AdbStatus;
  onUnauthorized: () => void;
};

type Gesture = {
  pointerId: number;
  reference: FrameReference;
  start: NormalizedPoint;
  clientX: number;
  clientY: number;
  startedAt: number;
};

type ActionResult = {
  state: string;
  action: string;
  postcondition_verified: boolean;
};

const SAFE_TEXT = /^[A-Za-z0-9 .,@_+\-]+$/;

const KEY_ACTIONS: ReadonlyArray<{ action: AndroidKeyAction; label: string }> = [
  { action: "home", label: "HOME" },
  { action: "back", label: "BACK" },
  { action: "recents", label: "RECENTES" },
  { action: "enter", label: "ENTER" },
  { action: "volume_up", label: "VOLUME +" },
  { action: "volume_down", label: "VOLUME −" },
  { action: "volume_mute", label: "MUDO" },
  { action: "wake", label: "ACORDAR" },
  { action: "sleep", label: "DORMIR" },
];

function connectionLabel(state: string): string {
  const labels: Record<string, string> = {
    idle: "inativo",
    connecting: "conectando",
    online: "online",
    reconnecting: "reconectando",
    offline: "offline",
    unauthorized: "sessão expirada",
    error: "erro",
  };
  return labels[state] ?? state;
}

function adbLabel(status: AdbStatus): string {
  const labels: Record<string, string> = {
    available: "disponível",
    unavailable: "indisponível",
    unauthorized: "não autorizado",
    connecting: "conectando",
    error: "erro",
  };
  return labels[status.state] ?? status.state;
}

function humanError(code: string): string {
  const labels: Record<string, string> = {
    STALE_FRAME: "O frame ficou antigo. Aguarde a próxima captura.",
    ROTATION_MISMATCH: "A orientação mudou. Aguarde a próxima captura.",
    ROTATION_UNKNOWN: "A rotação do Android não pôde ser confirmada.",
    FRAME_REQUIRED: "É necessário um frame atual para controlar o Android.",
    CONFIRMATION_REQUIRED: "Esta ação exige confirmação.",
    RATE_LIMITED: "Muitas ações em sequência. Aguarde um instante.",
    TEXT_NOT_ALLOWED: "O texto contém caracteres ainda não suportados.",
    CSRF_REJECTED: "A sessão de controle não pôde ser validada.",
    ORIGIN_REJECTED: "A origem desta página não foi autorizada.",
    UNAUTHORIZED: "A sessão expirou. Entre novamente.",
  };
  return labels[code] ?? `Ação não concluída: ${code}`;
}

function frameReference(frame: ScreenFrame): FrameReference | null {
  if (!isKnownRotation(frame.metadata.rotation)) return null;
  return {
    stream_id: frame.metadata.stream_id,
    frame_id: frame.metadata.frame_id,
    display_id: frame.metadata.display_id,
    rotation: frame.metadata.rotation,
    adb_target: frame.metadata.adb_target,
    adb_generation: frame.metadata.adb_generation,
  };
}

function newestAdbStatus(streamStatus?: AdbStatus | null, dashboardStatus?: AdbStatus): AdbStatus {
  if (!streamStatus) return dashboardStatus ?? { state: "unavailable", reason: "NOT_OBSERVED" };
  if (!dashboardStatus) return streamStatus;
  const streamTime = Date.parse(streamStatus.observed_at ?? "");
  const dashboardTime = Date.parse(dashboardStatus.observed_at ?? "");
  if (Number.isFinite(streamTime) && Number.isFinite(dashboardTime)) {
    return dashboardTime > streamTime ? dashboardStatus : streamStatus;
  }
  return dashboardStatus;
}

export function RemoteScreenPage({ role, csrfToken, dashboardAdb, onUnauthorized }: Props) {
  const stream = useScreenStream(true, onUnauthorized);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const gestureRef = useRef<Gesture | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [fullscreen, setFullscreen] = useState(false);
  const [now, setNow] = useState(Date.now());

  const adb = newestAdbStatus(stream.adbStatus, dashboardAdb);
  const frame = stream.frame;
  const reference = frame ? frameReference(frame) : null;
  const hasControlRole = role === "operator" || role === "admin";
  const freshnessWindow = Math.max(250, stream.frameMaxAgeSeconds * 1_000 - 500);
  const frameFresh = stream.confirmedAt !== null && now - stream.confirmedAt <= freshnessWindow;
  const canControl = hasControlRole
    && !busy
    && stream.connection === "online"
    && stream.frameConfirmed
    && frameFresh
    && adb.state === "available"
    && reference !== null;

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const changed = () => setFullscreen(document.fullscreenElement === viewportRef.current);
    document.addEventListener("fullscreenchange", changed);
    return () => document.removeEventListener("fullscreenchange", changed);
  }, []);

  const runAction = useCallback(async (path: string, body: Record<string, unknown>): Promise<boolean> => {
    setBusy(true);
    setMessage(null);
    try {
      const result = await api<ActionResult>(path, {
        method: "POST",
        headers: { "X-CSRF-Token": csrfToken },
        body: JSON.stringify(body),
      });
      setMessage(result.postcondition_verified
        ? `${result.action}: confirmado.`
        : `${result.action}: enviado, resultado ainda não verificado.`);
      return true;
    } catch (error) {
      const code = error instanceof ApiError ? error.code : "REQUEST_FAILED";
      setMessage(humanError(code));
      if (error instanceof ApiError && error.status === 401) onUnauthorized();
      return false;
    } finally {
      setBusy(false);
    }
  }, [csrfToken, onUnauthorized]);

  const currentReference = useCallback(() => {
    if (!canControl || !frame || !reference) {
      setMessage("Controle desabilitado até ADB e um frame atual estarem disponíveis.");
      return null;
    }
    return reference;
  }, [canControl, frame, reference]);

  const pointForEvent = useCallback((event: ReactPointerEvent<HTMLImageElement>) => {
    if (!viewportRef.current || !frame) return null;
    return pointInContainedFrame(
      event.clientX,
      event.clientY,
      viewportRef.current.getBoundingClientRect(),
      frame.metadata.width,
      frame.metadata.height,
    );
  }, [frame]);

  const pointerDown = (event: ReactPointerEvent<HTMLImageElement>) => {
    if (!canControl || event.button !== 0) return;
    const activeReference = currentReference();
    const point = pointForEvent(event);
    if (!point || !activeReference) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    gestureRef.current = {
      pointerId: event.pointerId,
      reference: activeReference,
      start: point,
      clientX: event.clientX,
      clientY: event.clientY,
      startedAt: performance.now(),
    };
  };

  const pointerUp = (event: ReactPointerEvent<HTMLImageElement>) => {
    const gesture = gestureRef.current;
    gestureRef.current = null;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    const end = pointForEvent(event);
    const base = currentReference();
    if (!end || !base) {
      setMessage("Gesto ignorado fora da área visível da tela.");
      return;
    }
    if (base.stream_id !== gesture.reference.stream_id || base.frame_id !== gesture.reference.frame_id) {
      setMessage("Gesto cancelado porque o frame mudou.");
      return;
    }
    event.preventDefault();
    const elapsed = performance.now() - gesture.startedAt;
    const distance = Math.hypot(event.clientX - gesture.clientX, event.clientY - gesture.clientY);
    if (distance >= 12) {
      void runAction("/api/v1/android/swipe", {
        ...base,
        start_x: gesture.start.x,
        start_y: gesture.start.y,
        end_x: end.x,
        end_y: end.y,
        duration_ms: Math.min(2_000, Math.max(100, Math.round(elapsed))),
      });
    } else if (elapsed >= 550) {
      void runAction("/api/v1/android/long-press", {
        ...base,
        x: gesture.start.x,
        y: gesture.start.y,
        duration_ms: Math.min(3_000, Math.max(500, Math.round(elapsed))),
      });
    } else {
      void runAction("/api/v1/android/tap", { ...base, x: end.x, y: end.y });
    }
  };

  const cancelGesture = () => {
    gestureRef.current = null;
  };

  const sendKey = (action: AndroidKeyAction) => {
    const base = currentReference();
    if (!base) return;
    if (action === "sleep" && !window.confirm("Dormir pode levar o aparelho à tela de bloqueio. Continuar?")) return;
    void runAction("/api/v1/android/key", {
      ...base,
      action,
      confirmed: action === "sleep",
    });
  };

  const submitText = (event: FormEvent) => {
    event.preventDefault();
    const base = currentReference();
    if (!base) return;
    if (!SAFE_TEXT.test(text) || text.length > 200) {
      setMessage("Use até 200 caracteres ASCII simples; quebras de linha e símbolos de shell são recusados.");
      return;
    }
    void runAction("/api/v1/android/text", { ...base, text }).then((sent) => {
      if (sent) setText("");
    });
  };

  const toggleFullscreen = async () => {
    setMessage(null);
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else if (viewportRef.current?.requestFullscreen) {
        await viewportRef.current.requestFullscreen();
      } else {
        setMessage("Tela cheia não é suportada por este navegador.");
      }
    } catch {
      setMessage("O navegador recusou a tela cheia.");
    }
  };

  const controlReason = useMemo(() => {
    if (!hasControlRole) return "Seu papel permite somente visualizar.";
    if (adb.state !== "available") return `ADB ${adbLabel(adb)}${adb.reason ? ` · ${adb.reason}` : ""}.`;
    if (!frame) return "Aguardando o primeiro frame.";
    if (!reference) return "Rotação não confirmada; controle bloqueado.";
    if (stream.ackPending) return "Frame exibido; aguardando confirmação do servidor.";
    if (!stream.frameConfirmed) return "Aguardando o frame ser exibido.";
    if (!frameFresh) return "Frame antigo; aguarde uma nova captura.";
    if (stream.connection !== "online") return "Stream desconectado.";
    return "Toque, arraste ou mantenha pressionado sobre a imagem.";
  }, [adb, frame, frameFresh, hasControlRole, reference, stream.ackPending, stream.connection, stream.frameConfirmed]);

  const aspectStyle = {
    "--frame-aspect": frame ? `${frame.metadata.width} / ${frame.metadata.height}` : "9 / 16",
  } as CSSProperties;

  return <section className="remote-page" aria-labelledby="remote-title">
    <div className="section-heading">
      <div>
        <p className="eyebrow">SCREENSHOT MVP · BAIXO FPS</p>
        <h2 id="remote-title">Tela remota</h2>
      </div>
      <div className="remote-actions">
        <button className="secondary-button" type="button" onClick={stream.reconnect}>Reconectar</button>
        <button className="secondary-button" type="button" onClick={() => void toggleFullscreen()} disabled={!frame}>Tela cheia</button>
      </div>
    </div>

    <div className="remote-status" aria-live="polite">
      <span className={`status-chip state-${stream.connection}`}>Stream: {connectionLabel(stream.connection)}</span>
      <span className={`status-chip state-${adb.state}`}>ADB: {adbLabel(adb)}</span>
      {adb.reason && <span className="status-detail">ADB: {adb.reason}</span>}
      {stream.lastError && <span className="status-detail">{stream.lastError}</span>}
    </div>

    <div className="remote-layout">
      <div className="screen-column">
        <div
          ref={viewportRef}
          className={`screen-viewport ${canControl ? "control-enabled" : ""}`}
          style={aspectStyle}
        >
          {frame
            ? <img
              className="screen-image"
              src={frame.objectUrl}
              alt="Captura atual da tela lógica do Android"
              draggable={false}
              onLoad={() => stream.confirmFrame(frame)}
              onError={() => stream.rejectFrame(frame)}
              onPointerDown={pointerDown}
              onPointerUp={pointerUp}
              onPointerCancel={cancelGesture}
              onContextMenu={(event) => event.preventDefault()}
            />
            : <div className="screen-placeholder">
              <strong>Aguardando captura</strong>
              <span>O painel continua disponível mesmo sem ADB.</span>
            </div>}
          {!stream.frameConfirmed && frame && <div className="frame-loading">
            {stream.ackPending ? "Confirmando frame…" : "Decodificando frame…"}
          </div>}
          <div className="fullscreen-overlay">
            <span>ADB {adbLabel(adb)}</span>
            <button type="button" onClick={() => void toggleFullscreen()}>{fullscreen ? "Sair" : "Tela cheia"}</button>
          </div>
        </div>

        <div className="frame-meta">
          <span>{frame ? `${frame.metadata.width} × ${frame.metadata.height}` : "Resolução aguardando"}</span>
          <span>{frame ? `${frame.metadata.orientation} · rotação ${frame.metadata.rotation ?? "?"}°` : "Orientação aguardando"}</span>
          <span>{frame ? `aspect ratio ${frame.metadata.aspect_ratio.toFixed(3)}` : "Aspect ratio aguardando"}</span>
          <span>{stream.fps.toFixed(1)} FPS configurado</span>
        </div>
      </div>

      <aside className="control-panel" aria-disabled={!canControl}>
        <div className="control-heading">
          <div>
            <span className={`dot ${canControl ? "online" : "degraded"}`} />
            <strong>Controle Android</strong>
          </div>
          <small>{controlReason}</small>
        </div>

        <div className="action-grid">
          {KEY_ACTIONS.map(({ action, label }) => <button
            key={action}
            type="button"
            className={action === "sleep" ? "danger-button" : "control-button"}
            disabled={!canControl}
            onClick={() => sendKey(action)}
          >{label}</button>)}
        </div>

        <form className="text-control" onSubmit={submitText}>
          <label htmlFor="android-text">Entrada de texto ASCII</label>
          <div>
            <input
              id="android-text"
              value={text}
              onChange={(event) => setText(event.target.value)}
              maxLength={200}
              placeholder="Texto simples"
              disabled={!canControl}
              autoComplete="off"
            />
            <button type="submit" disabled={!canControl || text.length === 0}>Enviar</button>
          </div>
          <small>Unicode completo ainda não é garantido.</small>
        </form>

        {message && <p className="action-message" role="status">{message}</p>}
      </aside>
    </div>
  </section>;
}
