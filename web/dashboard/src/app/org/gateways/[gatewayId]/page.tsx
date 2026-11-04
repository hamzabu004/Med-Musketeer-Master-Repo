import { GatewayDetail } from "@/features/org/gateway-detail";

export default async function Page({ params }: { params: Promise<{ gatewayId: string }> }) {
  const { gatewayId } = await params;
  return <GatewayDetail gatewayId={gatewayId} />;
}
