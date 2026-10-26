import { DoctorPatientDetail } from "@/features/doctor/doctor-patient-detail";

export default async function Page({ params }: { params: Promise<{ patientId: string }> }) {
  const { patientId } = await params;
  return <DoctorPatientDetail patientId={patientId} />;
}
