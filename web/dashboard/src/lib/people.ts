import type { Person } from "@/api/types";

/** Names live in ZITADEL, not the database: screens look them up in GET /directory (D14). A person
 * the directory does not return (ZITADEL unreachable, or out of the caller's view) has no name. */
export function personName(person: Person | undefined): string | null {
  if (!person) return null;
  const name = [person.given_name, person.family_name].filter(Boolean).join(" ");
  return name || null;
}

export function peopleById(people: Person[]): Map<string, Person> {
  return new Map(people.map((p) => [p.user_id, p]));
}

/** The directory, or none when it fails: names come from ZITADEL, and a page should still work
 * (with ids) while ZITADEL is unreachable. `named` says whether names could be read. */
export async function loadPeople(directory: () => Promise<Person[]>): Promise<{ people: Person[]; named: boolean }> {
  try {
    return { people: await directory(), named: true };
  } catch {
    return { people: [], named: false };
  }
}

export const NAMES_UNAVAILABLE = "Names could not be read from the identity provider, so people are shown by id.";
