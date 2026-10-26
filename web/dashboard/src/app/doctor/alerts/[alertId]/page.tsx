import { AlertDetail } from "@/features/doctor/alert-detail";

export default async function Page({ params }: { params: Promise<{ alertId: string }> }) {
  const { alertId } = await params;
  return <AlertDetail alertId={alertId} />;
}
