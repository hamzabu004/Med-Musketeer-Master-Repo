import { SegmentPage } from "@/features/care/segment-viewer";

export default async function Page({ params }: { params: Promise<{ patientId: string; segmentId: string }> }) {
  const { patientId, segmentId } = await params;
  return <SegmentPage segmentId={segmentId} back={{ href: `/doctor/patients/${patientId}`, label: "Back to the patient" }} />;
}
