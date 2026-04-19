// @ts-nocheck
import { readFile } from "node:fs/promises";
import type { PathLike } from "node:fs";

export type Vector = number[];

export interface Animal {
  name: string;
  speak(): string;
}

export type Result<T, E = Error> = { ok: true; value: T } | { ok: false; error: E };

export enum Direction {
  Up = "UP",
  Down = "DOWN",
  Left = "LEFT",
  Right = "RIGHT",
}

export class Dog implements Animal {
  constructor(public readonly name: string, private readonly age: number) {}

  speak(): string {
    return `Woof, I am ${this.name}`;
  }

  getAge(): number {
    return this.age;
  }
}

export function greet(name: string, greeting = "Hello"): string {
  return `${greeting}, ${name}!`;
}

export async function fetchData(url: string, timeout = 30): Promise<Uint8Array> {
  const response = await fetch(url, { signal: AbortSignal.timeout(timeout * 1000) });
  const buffer = await response.arrayBuffer();
  return new Uint8Array(buffer);
}

export const applyTransform = <T>(fn: (x: T) => T, value: T): T => fn(value);

export async function readFileContents(path: PathLike): Promise<string> {
  const contents = await readFile(path, "utf-8");
  return contents.trim();
}

export class Repository<T extends { id: number }> {
  private readonly items: Map<number, T> = new Map();

  async findById(id: number): Promise<T | undefined> {
    return this.items.get(id);
  }

  save(item: T): void {
    this.items.set(item.id, item);
  }
}
