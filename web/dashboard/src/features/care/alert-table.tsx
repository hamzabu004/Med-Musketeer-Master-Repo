"use client";

import Link from "next/link";
import type { Alert } from "@/api/types";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Status } from "@/components/ui/status";
import { Table, Td, THead, Tr } from "@/components/ui/table";
import { formatAgo, formatDateTime } from "@/lib/date-time";
import { beatLabel, confidence, labelize } from "@/lib/labels";
import { useRenderMarks } from "./render-mark";

/** Where the alert was classified: on the fixed path by the gateway, on the mobile path by the cloud. */
export function originLabel(origin: string): string {
  return origin === "gateway" ? "Gateway (fixed path)" : origin === "cloud" ? "Cloud (mobile path)" : labelize(origin);
}

export function AlertTable({
  alerts,
  patientName,
  detailHref,
  acknowledgedBy,
  onAcknowledge,
  isPending,
  empty,
}: {
  alerts: Alert[];
  /** Shown as a column when given (a doctor's inbox across patients). */
  patientName?: (alert: Alert) => { label: string; href: string };
  detailHref: (alert: Alert) => string | null;
  acknowledgedBy: (userId: string) => string;
  /** The doctor's acknowledge; absent for a patient, who can only read. */
  onAcknowledge?: (alert: Alert) => void;
  /** An acknowledge sent and not yet shown in the data: its button stays disabled. */
  isPending?: (alert: Alert) => boolean;
  empty: { title: string; description: string };
}) {
  useRenderMarks(alerts);
  if (!alerts.length) return <EmptyState title={empty.title} description={empty.description} />;
  const columns = ["Time", ...(patientName ? ["Patient"] : []), "Classification", "Classified by", "Status", ...(onAcknowledge ? [""] : [])];
  return (
    <Table label="Alerts" minWidth={patientName ? 820 : 700}>
      <THead columns={columns} />
      <tbody>
        {alerts.map((alert) => {
          const href = detailHref(alert);
          const patient = patientName?.(alert);
          return (
            <Tr key={alert.alert_id} className={alert.acknowledged_at ? undefined : "bg-[var(--color-surface-subtle)]"}>
              <Td className="whitespace-nowrap">
                {href ? <Link href={href} className="metric-number text-[var(--color-info)] underline-offset-2 hover:underline">{formatDateTime(alert.created_at)}</Link> : <span className="metric-number">{formatDateTime(alert.created_at)}</span>}
                <span className="block text-xs text-[var(--color-text-muted)]">{formatAgo(alert.created_at)}</span>
              </Td>
              {patient && <Td><Link href={patient.href} className="font-medium text-[var(--color-info)]">{patient.label}</Link></Td>}
              <Td>
                <span className="font-medium">{beatLabel(alert.label)}</span>
                <span className="block text-xs text-[var(--color-text-muted)]">Confidence {confidence(alert.confidence)}</span>
              </Td>
              <Td>{originLabel(alert.origin)}</Td>
              <Td>
                {alert.acknowledged_at ? (
                  <>
                    <Status label="Acknowledged" tone="healthy" />
                    <span className="block text-xs text-[var(--color-text-muted)]">{acknowledgedBy(alert.acknowledged_by!)}, {formatAgo(alert.acknowledged_at)}</span>
                  </>
                ) : (
                  <Status label="Unacknowledged" tone="warning" />
                )}
              </Td>
              {onAcknowledge && (
                <Td>
                  {!alert.acknowledged_at && (
                    <Button type="button" variant="secondary" disabled={isPending?.(alert)} onClick={() => onAcknowledge(alert)}>
                      {isPending?.(alert) ? "Acknowledging…" : "Acknowledge"}
                    </Button>
                  )}
                </Td>
              )}
            </Tr>
          );
        })}
      </tbody>
    </Table>
  );
}
