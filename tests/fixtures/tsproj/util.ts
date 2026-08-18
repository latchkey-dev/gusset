export function helper(n: number): number {
  return double(n) + 1;
}

function double(n: number): number {
  return n * 2;
}

export function unusedExport(): string {
  return "never imported";
}
