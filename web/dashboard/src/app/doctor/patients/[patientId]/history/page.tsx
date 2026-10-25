import { DoctorPatientHistory } from "@/features/doctor/doctor-patient-history";

export default async function Page({ params }: { params: Promise<{ patientId: string }> }) {
  const { patientId } = await params;
  return <DoctorPatientHistory patientId={patientId} />;
}
