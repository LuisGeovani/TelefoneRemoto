export type NormalizedPoint = { x: number; y: number };

type Rect = Pick<DOMRect, "left" | "top" | "width" | "height">;

export type ContainedFrameRect = Rect;

export function containedFrameRect(
  container: Rect,
  frameWidth: number,
  frameHeight: number,
): ContainedFrameRect | null {
  if (container.width <= 0 || container.height <= 0 || frameWidth <= 0 || frameHeight <= 0) {
    return null;
  }

  const scale = Math.min(container.width / frameWidth, container.height / frameHeight);
  const width = frameWidth * scale;
  const height = frameHeight * scale;
  return {
    left: container.left + (container.width - width) / 2,
    top: container.top + (container.height - height) / 2,
    width,
    height,
  };
}

export function pointInContainedFrame(
  clientX: number,
  clientY: number,
  container: Rect,
  frameWidth: number,
  frameHeight: number,
): NormalizedPoint | null {
  const rendered = containedFrameRect(container, frameWidth, frameHeight);
  if (!rendered) return null;
  const localX = clientX - rendered.left;
  const localY = clientY - rendered.top;
  const epsilon = Math.max(rendered.width, rendered.height, 1) * Number.EPSILON * 8;
  if (localX < -epsilon || localY < -epsilon || localX > rendered.width + epsilon || localY > rendered.height + epsilon) {
    return null;
  }

  return {
    x: Math.min(1, Math.max(0, localX / rendered.width)),
    y: Math.min(1, Math.max(0, localY / rendered.height)),
  };
}

export function isKnownRotation(rotation: number | null): rotation is 0 | 90 | 180 | 270 {
  return rotation === 0 || rotation === 90 || rotation === 180 || rotation === 270;
}
