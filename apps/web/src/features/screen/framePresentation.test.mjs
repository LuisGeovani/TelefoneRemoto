import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { FramePresentationMachine } from "./framePresentation.ts";

const frame = (id) => ({ id, width: 720, height: 1520 });

test("first frame keeps the placeholder until decode and acknowledgement finish", () => {
  const machine = new FramePresentationMachine();
  const first = frame("first");

  assert.equal(machine.snapshot().displayed, null);
  assert.equal(machine.begin(first), true);
  assert.equal(machine.snapshot().displayed, null);
  assert.equal(machine.decoded(first), true);
  assert.equal(machine.snapshot().displayed, null);
  assert.equal(machine.acknowledged(first, 100), null);
  assert.equal(machine.snapshot().displayed, first);
  assert.equal(machine.snapshot().displayedConfirmed, true);
});

test("next frame never replaces the displayed frame while decoding or awaiting ACK", () => {
  const machine = new FramePresentationMachine();
  const first = frame("first");
  const next = frame("next");
  machine.begin(first);
  machine.decoded(first);
  machine.acknowledged(first, 100);

  machine.begin(next);
  assert.equal(machine.snapshot().displayed, first);
  assert.equal(machine.snapshot().displayedConfirmed, true);
  machine.decoded(next);
  assert.equal(machine.snapshot().displayed, first);
  assert.equal(machine.snapshot().displayedConfirmed, true);
});

test("acknowledgement swaps directly from the old frame to the decoded frame", () => {
  const machine = new FramePresentationMachine();
  const first = frame("first");
  const next = frame("next");
  machine.begin(first);
  machine.decoded(first);
  machine.acknowledged(first, 100);
  machine.begin(next);
  machine.decoded(next);

  assert.equal(machine.acknowledged(next, 200), first);
  assert.deepEqual(machine.snapshot(), {
    displayed: next,
    candidate: null,
    candidatePhase: "none",
    displayedConfirmed: true,
    confirmedAt: 200,
  });
});

test("temporary candidate failure preserves the last valid displayed frame", () => {
  const machine = new FramePresentationMachine();
  const first = frame("first");
  const broken = frame("broken");
  machine.begin(first);
  machine.decoded(first);
  machine.acknowledged(first, 100);
  machine.begin(broken);

  assert.equal(machine.candidateFailed(broken), true);
  assert.equal(machine.snapshot().displayed, first);
  assert.equal(machine.snapshot().displayedConfirmed, true);
});

test("offline keeps the last frame visible but revokes its control authorization", () => {
  const machine = new FramePresentationMachine();
  const first = frame("first");
  machine.begin(first);
  machine.decoded(first);
  machine.acknowledged(first, 100);

  machine.invalidate(true);
  assert.equal(machine.snapshot().displayed, first);
  assert.equal(machine.snapshot().displayedConfirmed, false);
  assert.equal(machine.snapshot().confirmedAt, null);
});

test("reconnect preserves the stale image and atomically promotes the recovered frame", () => {
  const machine = new FramePresentationMachine();
  const first = frame("first");
  const recovered = frame("recovered");
  machine.begin(first);
  machine.decoded(first);
  machine.acknowledged(first, 100);
  machine.invalidate(true);

  machine.begin(recovered);
  assert.equal(machine.snapshot().displayed, first);
  machine.decoded(recovered);
  assert.equal(machine.snapshot().displayed, first);
  machine.acknowledged(recovered, 300);
  assert.equal(machine.snapshot().displayed, recovered);
  assert.equal(machine.snapshot().displayedConfirmed, true);
});

test("remote surface has no per-frame decode or loading overlay", async () => {
  const source = await readFile(new URL("./RemoteScreenPage.tsx", import.meta.url), "utf8");
  const stream = await readFile(new URL("./useScreenStream.ts", import.meta.url), "utf8");
  const styles = await readFile(new URL("../../styles.css", import.meta.url), "utf8");
  assert.doesNotMatch(source, /Decodificando frame|Confirmando frame|frame-loading/);
  assert.doesNotMatch(styles, /\.frame-loading\s*\{/);
  assert.match(source, /Aguardando primeira captura/);
  assert.match(source, /controlPresentation\(/);
  assert.doesNotMatch(source, /ackPending/);
  assert.match(stream, /image\.decode\(\)\.then\(decoded, decodeFailed\)/);
});
