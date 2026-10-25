import { ServiceError } from "@/types";

export function inOrganization<T extends { organizationId: string }>(items: T[], organizationId: string): T[] {
  return items.filter((item) => item.organizationId === organizationId);
}

export function findInOrganization<T extends { id: string; organizationId: string }>(
  items: T[],
  organizationId: string,
  id: string,
): T | undefined {
  return items.find((item) => item.id === id && item.organizationId === organizationId);
}

export function assertOwnedByOrganization(
  resource: { organizationId: string } | undefined,
  organizationId: string,
  message: string,
) {
  if (!resource || resource.organizationId !== organizationId) {
    throw new ServiceError("VALIDATION", message);
  }
}
