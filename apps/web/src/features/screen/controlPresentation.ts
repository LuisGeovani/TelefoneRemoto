export type ControlPresentationInput = Readonly<{
  hasControlRole: boolean;
  adbState: string;
  adbReason?: string;
  connection: string;
  hasFrame: boolean;
  hasReference: boolean;
  frameConfirmed: boolean;
  frameFresh: boolean;
}>;

export type ControlPresentation = Readonly<{
  help: string;
  status: string;
  statusState: "available" | "connecting" | "offline" | "error" | "unavailable";
}>;

const CONTROL_HELP = "Toque, arraste ou mantenha pressionado sobre a imagem.";

function connectionLabel(state: string): string {
  const labels: Record<string, string> = {
    idle: "inativo",
    connecting: "conectando",
    reconnecting: "reconectando",
    offline: "offline",
    unauthorized: "sessão expirada",
    error: "erro",
  };
  return labels[state] ?? state;
}

function adbLabel(state: string): string {
  const labels: Record<string, string> = {
    unavailable: "indisponível",
    unauthorized: "não autorizado",
    connecting: "conectando",
    error: "erro",
  };
  return labels[state] ?? state;
}

export function controlPresentation(input: ControlPresentationInput): ControlPresentation {
  const help = input.hasControlRole ? CONTROL_HELP : "Seu papel permite somente visualizar.";

  if (!input.hasControlRole) return { help, status: "Controle: somente visualização", statusState: "unavailable" };
  if (input.adbState !== "available") {
    return {
      help,
      status: `Controle: ADB ${adbLabel(input.adbState)}${input.adbReason ? ` · ${input.adbReason}` : ""}`,
      statusState: input.adbState === "connecting" ? "connecting" : input.adbState === "error" ? "error" : "unavailable",
    };
  }
  if (input.connection !== "online") {
    return {
      help,
      status: `Controle: stream ${connectionLabel(input.connection)}; bloqueado`,
      statusState: input.connection === "connecting" || input.connection === "reconnecting" ? "connecting" : input.connection === "error" ? "error" : "offline",
    };
  }
  if (!input.hasFrame) return { help, status: "Controle: aguardando primeira captura", statusState: "connecting" };
  if (!input.hasReference) return { help, status: "Controle: rotação não confirmada", statusState: "unavailable" };
  if (!input.frameConfirmed) return { help, status: "Controle: aguardando frame confirmado", statusState: "connecting" };
  if (!input.frameFresh) return { help, status: "Controle: frame antigo; aguardando captura", statusState: "unavailable" };
  return { help, status: "Controle: disponível", statusState: "available" };
}
