// Repository pattern: today reads JSON from disk, tomorrow reads Postgres.
// The UI depends on this interface, never on the file system directly.

import fs from "node:fs/promises";
import path from "node:path";
import type { Borrower } from "./types";

export interface BorrowerRepository {
  list(): Promise<Borrower[]>;
  get(id: string): Promise<Borrower | null>;
}

export class JsonBorrowerRepository implements BorrowerRepository {
  constructor(private dir: string) {}

  async list(): Promise<Borrower[]> {
    const entries = await fs.readdir(this.dir).catch(() => []);
    const out: Borrower[] = [];
    for (const f of entries) {
      if (!f.endsWith(".json")) continue;
      const raw = await fs.readFile(path.join(this.dir, f), "utf8");
      out.push(JSON.parse(raw) as Borrower);
    }
    return out.sort((a, b) => a.id.localeCompare(b.id));
  }

  async get(id: string): Promise<Borrower | null> {
    const file = path.join(this.dir, `${id}.json`);
    try {
      const raw = await fs.readFile(file, "utf8");
      return JSON.parse(raw) as Borrower;
    } catch {
      return null;
    }
  }
}

const OUTPUT_DIR =
  process.env.EXTRACTOR_OUTPUT_DIR ??
  path.join(process.cwd(), "data", "output");

export const repository: BorrowerRepository = new JsonBorrowerRepository(
  OUTPUT_DIR,
);
