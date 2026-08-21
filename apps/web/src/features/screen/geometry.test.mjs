import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { containedFrameRect, pointInContainedFrame } from "./geometry.ts";

test("portrait frame is fully contained and centered in a wide viewport", () => {
  const rendered = containedFrameRect({ left: 10, top: 20, width: 1000, height: 600 }, 720, 1520);
  assert.deepEqual(rendered, {
    left: 10 + (1000 - (720 * 600 / 1520)) / 2,
    top: 20,
    width: 720 * 600 / 1520,
    height: 600,
  });
});

test("landscape frame is fully contained and centered in a tall viewport", () => {
  const rendered = containedFrameRect({ left: 0, top: 0, width: 360, height: 800 }, 1920, 1080);
  assert.deepEqual(rendered, {
    left: 0,
    top: (800 - (1080 * 360 / 1920)) / 2,
    width: 360,
    height: 1080 * 360 / 1920,
  });
});

test("mapping uses only the actual contained image bounds", () => {
  const viewport = { left: 100, top: 50, width: 1000, height: 600 };
  const rendered = containedFrameRect(viewport, 720, 1520);
  assert.ok(rendered);

  assert.deepEqual(
    pointInContainedFrame(rendered.left, rendered.top, viewport, 720, 1520),
    { x: 0, y: 0 },
  );
  assert.deepEqual(
    pointInContainedFrame(
      rendered.left + rendered.width / 2,
      rendered.top + rendered.height / 2,
      viewport,
      720,
      1520,
    ),
    { x: 0.5, y: 0.5 },
  );
  assert.deepEqual(
    pointInContainedFrame(rendered.left + rendered.width, rendered.top + rendered.height, viewport, 720, 1520),
    { x: 1, y: 1 },
  );
});

test("clicks in horizontal and vertical letterbox areas are rejected", () => {
  assert.equal(
    pointInContainedFrame(20, 300, { left: 0, top: 0, width: 1000, height: 600 }, 720, 1520),
    null,
  );
  assert.equal(
    pointInContainedFrame(180, 20, { left: 0, top: 0, width: 360, height: 800 }, 1920, 1080),
    null,
  );
});

test("screen image is removed from grid sizing and always uses contain", async () => {
  const css = await readFile(new URL("../../styles.css", import.meta.url), "utf8");
  const block = css.match(/\.screen-image\s*\{([^}]*)\}/)?.[1] ?? "";
  assert.match(block, /position:\s*absolute/);
  assert.match(block, /inset:\s*0/);
  assert.match(block, /object-fit:\s*contain/);
  assert.match(block, /object-position:\s*center center/);
  assert.doesNotMatch(block, /object-fit:\s*cover/);
});
