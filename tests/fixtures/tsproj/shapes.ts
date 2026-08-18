export class Base {
  area(): number {
    return 0;
  }
}

export class Fancy extends Base {
  area(): number {
    return 2;
  }

  describe(): string {
    return "fancy";
  }
}
