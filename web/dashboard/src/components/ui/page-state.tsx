import { userMessage } from "@/api/errors";
import type { Resource } from "@/lib/use-resource";
import { ErrorState } from "./error-state";
import { Skeleton } from "./skeleton";

export function PageSkeleton({ label = "Loading" }: { label?: string }) {
  return (
    <div className="space-y-4" aria-busy="true" aria-label={label}>
      <Skeleton className="h-7 w-56" />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-20" />
        ))}
      </div>
      <Skeleton className="h-64" />
    </div>
  );
}

/** Renders `children(data)` once the resource is ready; loading and failure in between. */
export function Loaded<T>({ resource, children, label }: { resource: Resource<T>; children: (data: T) => React.ReactNode; label?: string }) {
  if (resource.status === "loading") return <PageSkeleton label={label} />;
  if (resource.status === "error") {
    return <ErrorState title="Could not load this page" description={userMessage(resource.error)} onRetry={resource.reload} />;
  }
  return <>{children(resource.data)}</>;
}
