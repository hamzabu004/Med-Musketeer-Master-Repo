import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";

export function DoctorPageSkeleton() {
  return (
    <div className="space-y-5" aria-label="Loading clinical monitoring information" aria-busy="true">
      <div className="space-y-2">
        <Skeleton className="h-7 w-64" />
        <Skeleton className="h-4 w-full max-w-lg" />
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
      </div>
      <Skeleton className="h-72" />
    </div>
  );
}

export function DoctorPageError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <ErrorState
      title="Clinical monitoring information unavailable"
      description={`${message} Try again to reload the simulated data.`}
      onRetry={onRetry}
    />
  );
}
