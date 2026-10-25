/** Sample-data mode: the world and the signed-in sample account, kept in sessionStorage so a reload
 * keeps what was done in this tab, and signing out starts afresh. */
import { createWorld, type World } from "./world";

const WORLD_KEY = "medmusketeer:dashboard:sample-world";
const USER_KEY = "medmusketeer:dashboard:sample-user";

function read(key: string): string | null {
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null) {
  try {
    if (value === null) window.sessionStorage.removeItem(key);
    else window.sessionStorage.setItem(key, value);
  } catch {
    // storage unavailable (private mode, blocked): the sample session lasts until reload
  }
}

let world: World | null = null;

export function sampleWorld(): World {
  if (!world) {
    const stored = read(WORLD_KEY);
    world = stored ? (JSON.parse(stored) as World) : createWorld();
  }
  return world;
}

export function saveSampleWorld() {
  if (world) write(WORLD_KEY, JSON.stringify(world));
}

export function sampleUserId(): string | null {
  return read(USER_KEY);
}

export function signInSample(userId: string) {
  write(USER_KEY, userId);
}

export function signOutSample() {
  write(USER_KEY, null);
  write(WORLD_KEY, null);
  world = null;
}
