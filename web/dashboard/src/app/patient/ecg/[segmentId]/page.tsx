import { SegmentPage } from "@/features/care/segment-viewer";

export default async function Page({ params }: { params: Promise<{ segmentId: string }> }) {
  const { segmentId } = await params;
  return <SegmentPage segmentId={segmentId} back={{ href: "/patient/ecg", label: "All your ECG" }} />;
}
