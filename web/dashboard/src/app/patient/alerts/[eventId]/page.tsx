import { PatientAlertDetails } from "@/features/patient/patient-alert-details";

export default async function Page({ params }: { params: Promise<{ eventId: string }> }) {
  const { eventId } = await params;
  return <PatientAlertDetails alertId={eventId} />;
}
