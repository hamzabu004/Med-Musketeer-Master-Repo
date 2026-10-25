import { AdminSecurityEventDetails } from "@/features/admin/admin-security-event-details";

export default async function Page({ params }: { params: Promise<{ eventId: string }> }) {
  const { eventId } = await params;
  return <AdminSecurityEventDetails eventId={eventId} />;
}
