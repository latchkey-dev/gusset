export interface Status { ok: boolean; }
export function makeStatus(): Status {
  return { ok: true };
}
