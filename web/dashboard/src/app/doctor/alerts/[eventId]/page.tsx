import { DoctorAlertDetails } from "@/features/doctor/doctor-alert-details";

export default async function Page({ params }: { params: Promise<{ eventId: string }> }) {
  const { eventId } = await params;
  return <DoctorAlertDetails alertId={eventId} />;
}
