export class Vault {
  async get(key: string) { return key; }
  async set(key: string, v: string) { return v; }
}
