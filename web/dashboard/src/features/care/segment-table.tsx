import Link from "next/link";
import type { Segment } from "@/api/types";
import { EmptyState } from "@/components/ui/empty-state";
import { Table, Td, THead, Tr } from "@/components/ui/table";
import { formatDateTime } from "@/lib/date-time";
import { segmentTitle } from "./segment-viewer";

export function segmentSeconds(segment: Pick<Segment, "started_at" | "ended_at">): number | null {
  return segment.ended_at ? Math.round((Date.parse(segment.ended_at) - Date.parse(segment.started_at)) / 1000) : null;
}

export function SegmentTable({ segments, href }: { segments: Segment[]; href: (segment: Segment) => string }) {
  if (!segments.length) return <EmptyState title="No ECG yet" description="Segments appear when the wearable raises an alert or a recording is made." />;
  return (
    <Table label="ECG segments" minWidth={560}>
      <THead columns={["Started", "Kind", "Length", ""]} />
      <tbody>
        {segments.map((s) => {
          const seconds = segmentSeconds(s);
          return (
            <Tr key={s.segment_id}>
              <Td className="metric-number whitespace-nowrap">{formatDateTime(s.started_at)}</Td>
              <Td>{segmentTitle(s)}</Td>
              <Td className="metric-number">{seconds === null ? "Recording…" : `${seconds} s`}</Td>
              <Td><Link href={href(s)} className="text-[var(--color-info)] underline">View ECG</Link></Td>
            </Tr>
          );
        })}
      </tbody>
    </Table>
  );
}
