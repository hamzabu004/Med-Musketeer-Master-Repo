import { DoctorPatientProfile } from "@/features/doctor/doctor-patient-profile";

export default async function Page({ params }: { params: Promise<{ patientId: string }> }) {
  const { patientId } = await params;
  return <DoctorPatientProfile patientId={patientId} />;
}
