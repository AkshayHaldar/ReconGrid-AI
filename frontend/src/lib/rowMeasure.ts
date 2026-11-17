/* Height of an observed row, in whole pixels, or undefined when the
   observer gave nothing usable. borderBoxSize is missing in older
   Safari/WebKit engines, where contentRect is the only size reported. */
export type RowSizeEntry = {
  borderBoxSize?: ReadonlyArray<{ blockSize: number }>;
  contentRect?: { height: number };
};

export function observedBlockSize(entry: RowSizeEntry | undefined): number | undefined {
  const box = entry?.borderBoxSize?.[0];
  if (box && Number.isFinite(box.blockSize)) return Math.round(box.blockSize);
  const h = entry?.contentRect?.height;
  if (typeof h === "number" && Number.isFinite(h) && h > 0) return Math.round(h);
  return undefined;
}
