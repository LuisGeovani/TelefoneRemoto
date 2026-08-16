export type AdbState = "available" | "unavailable" | "unauthorized" | "connecting" | "error";

export type AdbStatus = {
  state: AdbState | string;
  reason?: string | null;
  observed_at?: string;
  target?: string | null;
  transport?: string | null;
  model?: string | null;
};

export type FrameMetadata = {
  schema_version: 1;
  type: "frame";
  stream_id: string;
  frame_id: string;
  width: number;
  height: number;
  rotation: 0 | 90 | 180 | 270 | null;
  display_id: number;
  mime: "image/png";
  orientation: "portrait" | "landscape" | "square";
  aspect_ratio: number;
  observed_at: string;
  adb_target: string;
  adb_generation: number;
};

export type ScreenFrame = {
  metadata: FrameMetadata;
  objectUrl: string;
};

export type FrameAcknowledged = {
  schema_version: 1;
  type: "frame_acknowledged";
  stream_id: string;
  frame_id: string;
};

export type StreamConnectionState =
  | "idle"
  | "connecting"
  | "online"
  | "reconnecting"
  | "offline"
  | "unauthorized"
  | "error";

export type AndroidKeyAction =
  | "home"
  | "back"
  | "recents"
  | "enter"
  | "volume_up"
  | "volume_down"
  | "volume_mute"
  | "wake"
  | "sleep";

export type FrameReference = {
  stream_id: string;
  frame_id: string;
  display_id: number;
  rotation: 0 | 90 | 180 | 270;
  adb_target: string;
  adb_generation: number;
};
