import { PatientDetail } from "@/features/org/patient-detail";

export default async function Page({ params }: { params: Promise<{ patientId: string }> }) {
  const { patientId } = await params;
  return <PatientDetail patientId={patientId} />;
}
