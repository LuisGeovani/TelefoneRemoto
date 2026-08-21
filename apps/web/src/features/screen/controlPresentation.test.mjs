import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { controlPresentation } from "./controlPresentation.ts";

const normal = () => ({
  hasControlRole: true,
  adbState: "available",
  connection: "online",
  hasFrame: true,
  hasReference: true,
  frameConfirmed: true,
  frameFresh: true,
});

test("normal control help stays stable across frame protocol transitions", () => {
  const baseline = controlPresentation(normal());
  const nextFrameDecoding = controlPresentation(normal());
  const nextFrameAwaitingAcknowledgement = controlPresentation(normal());
  const nextFramePromoted = controlPresentation(normal());

  assert.equal(baseline.help, "Toque, arraste ou mantenha pressionado sobre a imagem.");
  assert.equal(nextFrameDecoding.help, baseline.help);
  assert.equal(nextFrameAwaitingAcknowledgement.help, baseline.help);
  assert.equal(nextFramePromoted.help, baseline.help);
  assert.equal(baseline.status, "Controle: disponível");
});

test("normal control presentation does not depend on frame id, FPS, decode, or ACK state", async () => {
  const first = controlPresentation(normal());
  const afterUnrelatedStreamUpdates = controlPresentation({ ...normal(), frameFresh: true });
  const source = await readFile(new URL("./controlPresentation.ts", import.meta.url), "utf8");

  assert.deepEqual(afterUnrelatedStreamUpdates, first);
  assert.doesNotMatch(source, /ackPending|frame_id|fps|decode/i);
});

test("offline changes the discrete status but keeps interaction help and the preserved frame context", () => {
  const offline = controlPresentation({ ...normal(), connection: "offline" });

  assert.equal(offline.help, "Toque, arraste ou mantenha pressionado sobre a imagem.");
  assert.equal(offline.status, "Controle: stream offline; bloqueado");
  assert.equal(offline.statusState, "offline");
});

test("first frame and stale frame use status without replacing normal interaction help", () => {
  const waiting = controlPresentation({ ...normal(), hasFrame: false, hasReference: false, frameConfirmed: false, frameFresh: false });
  const stale = controlPresentation({ ...normal(), frameFresh: false });

  assert.equal(waiting.help, "Toque, arraste ou mantenha pressionado sobre a imagem.");
  assert.equal(waiting.status, "Controle: aguardando primeira captura");
  assert.equal(stale.help, waiting.help);
  assert.equal(stale.status, "Controle: frame antigo; aguardando captura");
});
