import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";

export function AdminPageSkeleton() {
  return (
    <div className="space-y-5" aria-label="Loading administration information" aria-busy="true">
      <div className="space-y-2"><Skeleton className="h-7 w-64" /><Skeleton className="h-4 w-full max-w-xl" /></div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => <Skeleton key={index} className="h-24" />)}
      </div>
      <Skeleton className="h-72" />
    </div>
  );
}

export function AdminPageError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <ErrorState title="Administration data unavailable" description={`${message} Try again to reload the simulated data.`} onRetry={onRetry} />;
}
