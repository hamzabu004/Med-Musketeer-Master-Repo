import { OrganisationDetail } from "@/features/system/organisation-detail";

export default async function Page({ params }: { params: Promise<{ orgId: string }> }) {
  const { orgId } = await params;
  return <OrganisationDetail orgId={orgId} />;
}
