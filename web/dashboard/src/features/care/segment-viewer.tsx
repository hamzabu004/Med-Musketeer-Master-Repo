"use client";

import Link from "next/link";
import { useMemo } from "react";
import type { SegmentDetail } from "@/api/types";
import { useData } from "@/auth/session";
import { ECGWaveform } from "@/components/charts/ecg-waveform";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { SectionTitle } from "@/components/ui/metric";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { RecordId } from "@/components/ui/record-id";
import { Table, Td, THead, Tr } from "@/components/ui/table";
import { formatDateTime } from "@/lib/date-time";
import { beatLabel, confidence, labelize } from "@/lib/labels";
import { stitchChunks } from "@/lib/ecg";
import { useResource } from "@/lib/use-resource";

export function segmentTitle(segment: Pick<SegmentDetail, "kind">): string {
  return segment.kind === "recording" ? "On-demand recording" : segment.kind === "alert" ? "Alert segment" : `${labelize(segment.kind)} segment`;
}

/** A segment's ECG and classifications, decoded from its int16le-base64 chunks. */
export function SegmentStrip({ segment }: { segment: SegmentDetail }) {
  const samples = useMemo(() => stitchChunks(segment.chunks), [segment.chunks]);
  const classifications = [...segment.classifications].sort((a, b) => a.created_at.localeCompare(b.created_at));
  return (
    <div className="space-y-4">
      <Card className="p-4">
        <ECGWaveform samples={samples} fsHz={segment.fs_hz} label={`${segmentTitle(segment)}, ${formatDateTime(segment.started_at)}`} />
      </Card>
      <SectionTitle>Classifications</SectionTitle>
      {classifications.length ? (
        <Table label="Classifications" minWidth={620}>
          <THead columns={["Classified by", "Model", "Result", "Confidence", "At"]} />
          <tbody>
            {classifications.map((c) => (
              <Tr key={c.classification_id}>
                <Td>{labelize(c.source)}</Td>
                <Td className="font-mono text-xs">{c.model_version}</Td>
                <Td className="font-medium">{beatLabel(c.label)}</Td>
                <Td className="metric-number">{confidence(c.confidence)}</Td>
                <Td className="metric-number whitespace-nowrap">{formatDateTime(c.created_at)}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      ) : (
        <EmptyState title="Not classified" description="No model has classified this segment." />
      )}
      <p className="text-xs text-[var(--color-text-muted)]">
        The wearable screens each segment (normal or abnormal); the gateway, or on the mobile path the cloud, then names the beat class. Model output is a research aid, not a diagnosis.
      </p>
    </div>
  );
}

export function SegmentPage({ segmentId, back }: { segmentId: string; back: { href: string; label: string } }) {
  const { data } = useData();
  const resource = useResource(() => data.care.segment(segmentId), [segmentId]);
  return (
    <section className="mx-auto max-w-6xl space-y-5">
      <Loaded resource={resource} label="Loading the ECG">
        {(segment) => (
          <>
            <PageIntro
              title={segmentTitle(segment)}
              description={`${formatDateTime(segment.started_at)}${segment.ended_at ? ` to ${formatDateTime(segment.ended_at)}` : ", still recording"} · ${segment.chunks.length} chunks at ${segment.fs_hz} Hz`}
            />
            <p className="text-sm">
              <Link href={back.href} className="text-[var(--color-info)] underline">{back.label}</Link>
              <span className="ml-3 text-xs text-[var(--color-text-muted)]">Wearable <RecordId id={segment.device_id} /></span>
            </p>
            <SegmentStrip segment={segment} />
          </>
        )}
      </Loaded>
    </section>
  );
}
