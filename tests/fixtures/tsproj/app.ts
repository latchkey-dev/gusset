import { helper } from "./util";
import { Fancy } from "./shapes";

const fmt = (n: number): string => "value: " + n;

export function main(): string {
  const f = new Fancy();
  const x = helper(3);
  return fmt(x) + f.describe();
}
