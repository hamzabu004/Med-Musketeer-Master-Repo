import { DeviceDetail } from "@/features/system/device-detail";

export default async function Page({ params }: { params: Promise<{ deviceId: string }> }) {
  const { deviceId } = await params;
  return <DeviceDetail deviceId={deviceId} />;
}
