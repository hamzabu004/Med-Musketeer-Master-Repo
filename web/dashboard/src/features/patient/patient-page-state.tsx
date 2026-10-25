import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";

export function PatientPageSkeleton() {
  return (
    <div className="space-y-5" aria-label="Loading patient information" aria-busy="true">
      <div className="space-y-2">
        <Skeleton className="h-7 w-56" />
        <Skeleton className="h-4 w-full max-w-md" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
      </div>
      <Skeleton className="h-56" />
    </div>
  );
}

export function PatientPageError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <ErrorState
      title="Patient information unavailable"
      description={`${message} Try again to reload the simulated data.`}
      onRetry={onRetry}
    />
  );
}
