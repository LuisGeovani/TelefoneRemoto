import { useCallback, useEffect, useRef, useState } from "react";

import type { AdbStatus, FrameAcknowledged, FrameMetadata, ScreenFrame, StreamConnectionState } from "./types";

const MAX_FRAME_BYTES = 24 * 1024 * 1024;
const ALLOWED_ROTATIONS = new Set([0, 90, 180, 270]);
const ALLOWED_ADB_STATES = new Set(["available", "unavailable", "unauthorized", "connecting", "error"]);
const IDENTIFIER = /^[A-Za-z0-9-]{1,80}$/;
const ADB_TARGET = /^[A-Za-z0-9._:\[\]%-]{1,200}$/;

type StreamStatusMessage = {
  schema_version: 1;
  type: "stream_status";
  state: string;
  stream_id: string;
  fps: number;
  frame_max_age_seconds: number;
  adb: AdbStatus;
};

type StreamErrorMessage = {
  schema_version: 1;
  type: "stream_error";
  code: string;
  adb: AdbStatus;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isAdbStatus(value: unknown): value is AdbStatus {
  return isRecord(value) && typeof value.state === "string" && ALLOWED_ADB_STATES.has(value.state);
}

function isFrameMetadata(value: unknown): value is FrameMetadata {
  if (!isRecord(value)) return false;
  const rotation = value.rotation;
  return value.schema_version === 1
    && value.type === "frame"
    && typeof value.stream_id === "string"
    && IDENTIFIER.test(value.stream_id)
    && typeof value.frame_id === "string"
    && IDENTIFIER.test(value.frame_id)
    && Number.isInteger(value.width)
    && Number(value.width) > 0
    && Number(value.width) <= 16384
    && Number.isInteger(value.height)
    && Number(value.height) > 0
    && Number(value.height) <= 16384
    && (rotation === null || (typeof rotation === "number" && ALLOWED_ROTATIONS.has(rotation)))
    && value.display_id === 0
    && value.mime === "image/png"
    && (value.orientation === "portrait" || value.orientation === "landscape" || value.orientation === "square")
    && typeof value.aspect_ratio === "number"
    && Number.isFinite(value.aspect_ratio)
    && value.aspect_ratio > 0
    && typeof value.observed_at === "string"
    && typeof value.adb_target === "string"
    && ADB_TARGET.test(value.adb_target)
    && Number.isInteger(value.adb_generation)
    && Number(value.adb_generation) >= 1;
}

function isStreamStatus(value: unknown): value is StreamStatusMessage {
  return isRecord(value)
    && value.schema_version === 1
    && value.type === "stream_status"
    && typeof value.state === "string"
    && typeof value.stream_id === "string"
    && IDENTIFIER.test(value.stream_id)
    && typeof value.fps === "number"
    && Number.isFinite(value.fps)
    && value.fps >= 0.2
    && value.fps <= 2
    && typeof value.frame_max_age_seconds === "number"
    && Number.isFinite(value.frame_max_age_seconds)
    && value.frame_max_age_seconds >= 1
    && value.frame_max_age_seconds <= 15
    && isAdbStatus(value.adb);
}

function isStreamError(value: unknown): value is StreamErrorMessage {
  return isRecord(value)
    && value.schema_version === 1
    && value.type === "stream_error"
    && typeof value.code === "string"
    && isAdbStatus(value.adb);
}

function isFrameAcknowledged(value: unknown): value is FrameAcknowledged {
  return isRecord(value)
    && value.schema_version === 1
    && value.type === "frame_acknowledged"
    && typeof value.stream_id === "string"
    && IDENTIFIER.test(value.stream_id)
    && typeof value.frame_id === "string"
    && IDENTIFIER.test(value.frame_id);
}

function websocketUrl(): string {
  const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${window.location.host}/api/v1/screen/ws`;
}

export function useScreenStream(enabled: boolean, onUnauthorized: () => void) {
  const [connection, setConnection] = useState<StreamConnectionState>("idle");
  const [frame, setFrame] = useState<ScreenFrame | null>(null);
  const [frameConfirmed, setFrameConfirmed] = useState(false);
  const [ackPending, setAckPending] = useState(false);
  const [confirmedAt, setConfirmedAt] = useState<number | null>(null);
  const [adbStatus, setAdbStatus] = useState<AdbStatus | null>(null);
  const [streamId, setStreamId] = useState<string | null>(null);
  const [fps, setFps] = useState(1);
  const [frameMaxAgeSeconds, setFrameMaxAgeSeconds] = useState(5);
  const [lastError, setLastError] = useState<string | null>(null);
  const [generation, setGeneration] = useState(0);

  const socketRef = useRef<WebSocket | null>(null);
  const candidateRef = useRef<ScreenFrame | null>(null);
  const confirmedFrameRef = useRef<ScreenFrame | null>(null);
  const confirmedUrlRef = useRef<string | null>(null);
  const ackSentRef = useRef<{ streamId: string; frameId: string } | null>(null);
  const urlsRef = useRef(new Set<string>());

  const clearFrameState = useCallback(() => {
    for (const url of urlsRef.current) URL.revokeObjectURL(url);
    urlsRef.current.clear();
    candidateRef.current = null;
    confirmedFrameRef.current = null;
    confirmedUrlRef.current = null;
    ackSentRef.current = null;
    setFrame(null);
    setFrameConfirmed(false);
    setAckPending(false);
    setConfirmedAt(null);
  }, []);

  useEffect(() => {
    if (!enabled) {
      setConnection("idle");
      setFrame(null);
      setFrameConfirmed(false);
      setAckPending(false);
      setConfirmedAt(null);
      setStreamId(null);
      setAdbStatus(null);
      setFps(1);
      setFrameMaxAgeSeconds(5);
      setLastError(null);
      return;
    }

    let disposed = false;
    let socket: WebSocket | null = null;
    let retryTimer: number | null = null;
    let attempt = 0;
    let pendingMetadata: FrameMetadata | null = null;
    let activeStreamId: string | null = null;

    const revoke = (url: string | null) => {
      if (url && urlsRef.current.delete(url)) URL.revokeObjectURL(url);
    };

    const clearFrames = () => {
      pendingMetadata = null;
      clearFrameState();
    };

    const protocolFailure = (code: string, currentSocket: WebSocket) => {
      clearFrames();
      setLastError(code);
      setConnection("error");
      if (currentSocket.readyState === WebSocket.OPEN) currentSocket.close(4000, "PROTOCOL_ERROR");
    };

    const scheduleReconnect = () => {
      if (disposed || retryTimer !== null) return;
      attempt += 1;
      setConnection("reconnecting");
      const delay = Math.min(10_000, 500 * (2 ** Math.min(attempt - 1, 5))) + Math.floor(Math.random() * 250);
      retryTimer = window.setTimeout(() => {
        retryTimer = null;
        open();
      }, delay);
    };

    const open = () => {
      if (disposed) return;
      setConnection(attempt === 0 ? "connecting" : "reconnecting");
      clearFrames();
      activeStreamId = null;
      setStreamId(null);
      setAdbStatus(null);
      setFps(1);
      setFrameMaxAgeSeconds(5);
      const currentSocket = new WebSocket(websocketUrl());
      socket = currentSocket;
      currentSocket.binaryType = "blob";
      socketRef.current = currentSocket;

      currentSocket.onopen = () => {
        if (!disposed) setLastError(null);
      };

      currentSocket.onmessage = (event: MessageEvent<unknown>) => {
        if (disposed || currentSocket !== socketRef.current) return;
        if (typeof event.data === "string") {
          let message: unknown;
          try {
            message = JSON.parse(event.data);
          } catch {
            protocolFailure("INVALID_STREAM_JSON", currentSocket);
            return;
          }
          if (isStreamStatus(message)) {
            attempt = 0;
            activeStreamId = message.stream_id;
            setConnection("online");
            setStreamId(message.stream_id);
            setFps(message.fps);
            setFrameMaxAgeSeconds(message.frame_max_age_seconds);
            setAdbStatus(message.adb);
            setLastError(null);
            return;
          }
          if (isStreamError(message)) {
            clearFrames();
            setAdbStatus(message.adb);
            setLastError(message.code);
            return;
          }
          if (isFrameAcknowledged(message)) {
            const candidate = candidateRef.current;
            const sent = ackSentRef.current;
            if (!candidate
              || !sent
              || message.stream_id !== activeStreamId
              || message.stream_id !== candidate.metadata.stream_id
              || message.frame_id !== candidate.metadata.frame_id
              || message.stream_id !== sent.streamId
              || message.frame_id !== sent.frameId) {
              protocolFailure("INVALID_FRAME_ACKNOWLEDGEMENT", currentSocket);
              return;
            }
            const previousUrl = confirmedUrlRef.current;
            confirmedFrameRef.current = candidate;
            confirmedUrlRef.current = candidate.objectUrl;
            ackSentRef.current = null;
            setFrame(candidate);
            setFrameConfirmed(true);
            setAckPending(false);
            setConfirmedAt(Date.now());
            setLastError(null);
            if (previousUrl && previousUrl !== candidate.objectUrl) revoke(previousUrl);
            return;
          }
          if (isFrameMetadata(message)
            && pendingMetadata === null
            && ackSentRef.current === null
            && message.stream_id === activeStreamId) {
            pendingMetadata = message;
            return;
          }
          protocolFailure("INVALID_STREAM_MESSAGE", currentSocket);
          return;
        }

        if (pendingMetadata === null) {
          protocolFailure("FRAME_METADATA_REQUIRED", currentSocket);
          return;
        }
        const blob = event.data instanceof Blob
          ? event.data
          : new Blob([event.data as BlobPart], { type: pendingMetadata.mime });
        if (blob.size === 0 || blob.size > MAX_FRAME_BYTES) {
          pendingMetadata = null;
          protocolFailure("INVALID_FRAME_SIZE", currentSocket);
          return;
        }
        const typedBlob = blob.type === pendingMetadata.mime
          ? blob
          : new Blob([blob], { type: pendingMetadata.mime });
        const next: ScreenFrame = {
          metadata: pendingMetadata,
          objectUrl: URL.createObjectURL(typedBlob),
        };
        pendingMetadata = null;
        urlsRef.current.add(next.objectUrl);
        const oldCandidate = candidateRef.current;
        if (oldCandidate && oldCandidate.objectUrl !== confirmedUrlRef.current) revoke(oldCandidate.objectUrl);
        candidateRef.current = next;
        setFrame(next);
        setFrameConfirmed(false);
        setAckPending(false);
      };

      currentSocket.onerror = () => {
        if (!disposed) {
          clearFrames();
          setLastError("STREAM_CONNECTION_ERROR");
        }
      };

      currentSocket.onclose = (event) => {
        if (currentSocket === socketRef.current) socketRef.current = null;
        clearFrames();
        activeStreamId = null;
        setStreamId(null);
        setAdbStatus(null);
        setFps(1);
        setFrameMaxAgeSeconds(5);
        if (disposed) return;
        if (event.code === 4401) {
          setConnection("unauthorized");
          setLastError("UNAUTHORIZED");
          onUnauthorized();
          return;
        }
        if (event.code === 4403 || event.code === 4400 || event.code === 4429) {
          setConnection("error");
          setLastError(event.reason || "STREAM_REJECTED");
          return;
        }
        setConnection("offline");
        scheduleReconnect();
      };
    };

    setFrame(null);
    setFrameConfirmed(false);
    setAckPending(false);
    setConfirmedAt(null);
    setStreamId(null);
    open();

    return () => {
      disposed = true;
      if (retryTimer !== null) window.clearTimeout(retryTimer);
      if (socket) {
        socket.onclose = null;
        socket.close(1000, "PAGE_CLOSED");
      }
      if (socketRef.current === socket) socketRef.current = null;
      for (const url of urlsRef.current) URL.revokeObjectURL(url);
      urlsRef.current.clear();
      candidateRef.current = null;
      confirmedFrameRef.current = null;
      confirmedUrlRef.current = null;
      ackSentRef.current = null;
    };
  }, [clearFrameState, enabled, generation, onUnauthorized]);

  const confirmFrame = useCallback((expected: ScreenFrame) => {
    const candidate = candidateRef.current;
    const confirmed = confirmedFrameRef.current;
    const socket = socketRef.current;
    if (!candidate
      || candidate.metadata.frame_id !== expected.metadata.frame_id
      || candidate.metadata.stream_id !== expected.metadata.stream_id
      || (ackSentRef.current?.streamId === expected.metadata.stream_id
        && ackSentRef.current.frameId === expected.metadata.frame_id)
      || (confirmed?.metadata.stream_id === expected.metadata.stream_id
        && confirmed.metadata.frame_id === expected.metadata.frame_id)
      || socket?.readyState !== WebSocket.OPEN) {
      return;
    }
    try {
      socket.send(JSON.stringify({
        type: "frame_ack",
        stream_id: candidate.metadata.stream_id,
        frame_id: candidate.metadata.frame_id,
      }));
    } catch {
      clearFrameState();
      setLastError("FRAME_ACK_SEND_FAILED");
      socket.close(4001, "FRAME_ACK_SEND_FAILED");
      return;
    }
    ackSentRef.current = {
      streamId: candidate.metadata.stream_id,
      frameId: candidate.metadata.frame_id,
    };
    setAckPending(true);
    setFrameConfirmed(false);
  }, [clearFrameState]);

  const rejectFrame = useCallback((expected: ScreenFrame) => {
    const candidate = candidateRef.current;
    if (!candidate || candidate.metadata.frame_id !== expected.metadata.frame_id) return;
    clearFrameState();
    setLastError("FRAME_DECODE_FAILED");
    socketRef.current?.close(4001, "FRAME_DECODE_FAILED");
  }, [clearFrameState]);

  const reconnect = useCallback(() => {
    setGeneration((value) => value + 1);
  }, []);

  return {
    connection,
    frame,
    frameConfirmed,
    ackPending,
    confirmedAt,
    adbStatus,
    streamId,
    fps,
    frameMaxAgeSeconds,
    lastError,
    confirmFrame,
    rejectFrame,
    reconnect,
  };
}
