/** Where the dashboard's data comes from, and what that source can serve.
 *
 * NEXT_PUBLIC_DATA_SOURCE=api (default): the cloud API at NEXT_PUBLIC_API_URL, signed in through
 * ZITADEL. =mock: sample data in the browser, for a deployment without the cloud. The two are never
 * mixed: in API mode a capability the cloud does not serve yet shows as unavailable, not as sample data. */
export type DataSourceKind = "api" | "mock";

export const dataSource: DataSourceKind = process.env.NEXT_PUBLIC_DATA_SOURCE === "mock" ? "mock" : "api";

export const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Features whose cloud endpoints are not built yet (see docs/decisions/cloud-backend.md, D9). */
export type Capability = "ecgRequests" | "attackTests" | "alertStream";

const servedByApi: Record<Capability, boolean> = {
  ecgRequests: false, // on-demand ECG: start/stop design open
  attackTests: false, // Iteration 5
  alertStream: false, // alert push needs ingestion (Slice 5); the dashboard polls meanwhile
};

export function isAvailable(capability: Capability, source: DataSourceKind = dataSource): boolean {
  return source === "mock" || servedByApi[capability];
}
