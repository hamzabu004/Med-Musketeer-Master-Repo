import { Card } from "@/components/ui/card";

export function PatientIdentity({
  name,
  clinicianName,
}: {
  name: string;
  clinicianName?: string | null;
}) {
  return (
    <Card className="p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">Patient</p>
      <p className="mt-1 text-lg font-semibold">{name}</p>
      <p className="mt-2 text-sm text-[var(--color-text-muted)]">
        Assigned clinician: <span className="text-[var(--color-text)]">{clinicianName ?? "Not assigned"}</span>
      </p>
    </Card>
  );
}
