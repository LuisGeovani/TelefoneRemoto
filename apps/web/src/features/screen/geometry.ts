export type NormalizedPoint = { x: number; y: number };

type Rect = Pick<DOMRect, "left" | "top" | "width" | "height">;

export function pointInContainedFrame(
  clientX: number,
  clientY: number,
  container: Rect,
  frameWidth: number,
  frameHeight: number,
): NormalizedPoint | null {
  if (container.width <= 0 || container.height <= 0 || frameWidth <= 0 || frameHeight <= 0) {
    return null;
  }

  const containerRatio = container.width / container.height;
  const frameRatio = frameWidth / frameHeight;
  let renderedWidth = container.width;
  let renderedHeight = container.height;
  let offsetX = 0;
  let offsetY = 0;

  if (containerRatio > frameRatio) {
    renderedWidth = container.height * frameRatio;
    offsetX = (container.width - renderedWidth) / 2;
  } else if (containerRatio < frameRatio) {
    renderedHeight = container.width / frameRatio;
    offsetY = (container.height - renderedHeight) / 2;
  }

  const localX = clientX - container.left - offsetX;
  const localY = clientY - container.top - offsetY;
  if (localX < 0 || localY < 0 || localX > renderedWidth || localY > renderedHeight) {
    return null;
  }

  return {
    x: Math.min(1, Math.max(0, localX / renderedWidth)),
    y: Math.min(1, Math.max(0, localY / renderedHeight)),
  };
}

export function isKnownRotation(rotation: number | null): rotation is 0 | 90 | 180 | 270 {
  return rotation === 0 || rotation === 90 || rotation === 180 || rotation === 270;
}
