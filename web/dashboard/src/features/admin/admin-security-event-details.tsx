"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageIntro } from "@/components/ui/page-intro";
import { formatDateTime } from "@/lib/date-time";
import { services } from "@/services";
import type { SecurityEvent } from "@/types";
import { AdminPageError, AdminPageSkeleton } from "./admin-page-state";
import { labelize, LabeledStatus } from "./admin-ui";

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "success"; event: SecurityEvent | null; organizationId: string };

export function AdminSecurityEventDetails({ eventId }: { eventId: string }) {
  const [state, setState] = useState<State>({ status: "loading" });
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [request, setRequest] = useState(0);

  useEffect(() => {
    let active = true;
    const session = services.auth.getSession();

    if (!session || session.role !== "admin") {
      setState({ status: "error", message: "An Organization Administrator session is required." });
      return;
    }

    services.security
      .getEvent(session.organizationId, eventId)
      .then((event) => active && setState({ status: "success", event, organizationId: session.organizationId }))
      .catch((error: unknown) => {
        if (!active) return;
        setState({ status: "error", message: error instanceof Error ? error.message : "Event unavailable." });
      });

    return () => {
      active = false;
    };
  }, [eventId, request]);

  if (state.status === "loading") return <AdminPageSkeleton />;
  if (state.status === "error") {
    return (
      <AdminPageError
        message={state.message}
        onRetry={() => {
          setState({ status: "loading" });
          setRequest((value) => value + 1);
        }}
      />
    );
  }
  if (!state.event) {
    return (
      <EmptyState
        title="Security event not found"
        description="This event does not exist in this organization's deterministic dataset."
      />
    );
  }

  const event = state.event;

  async function update(action: "acknowledge" | "resolve") {
    if (state.status !== "success") return;
    setSaving(true);
    setMessage("");
    try {
      const updated =
        action === "acknowledge"
          ? await services.security.acknowledge(state.organizationId, event.id)
          : await services.security.resolve(state.organizationId, event.id);
      setState({ ...state, event: updated });
      setMessage(`Security event ${action === "acknowledge" ? "acknowledged" : "resolved"} in browser state.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Event update failed.");
    } finally {
      setSaving(false);
    }
  }

  const fields: [[string, string], ...[string, string][]] = [
    ["Event ID", event.id],
    ["Type", labelize(event.type)],
    ["Timestamp", formatDateTime(event.timestamp)],
    ["Source", event.source],
    ["Destination", event.destination ?? "Not recorded"],
    ["Monitoring Station", event.monitoringStationId ?? "Not associated"],
    ["Risk level", labelize(event.severity)],
    ["Detection mechanism", event.detectionMechanism],
    ["Response", labelize(event.response)],
  ];

  return (
    <section className="mx-auto max-w-5xl space-y-5">
      <PageIntro
        title="Security Event Details"
        description="A deterministic simulated security record; no live enforcement or production investigation is performed."
        actions={
          <Link className="text-sm font-medium text-[var(--color-info)] underline-offset-2 hover:underline" href="/admin/security/ids-ips">
            Back to IDS / IPS
          </Link>
        }
      />
      <Card className="p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="font-semibold">{event.id}</h3>
          <LabeledStatus value={event.status} />
        </div>
        <dl className="mt-5 grid gap-4 sm:grid-cols-2">
          {fields.map(([label, value]) => (
            <div key={label}>
              <dt className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">{label}</dt>
              <dd className="mt-1 text-sm metric-number">{value}</dd>
            </div>
          ))}
        </dl>
      </Card>
      {message && (
        <p role="status" className="border-l-2 border-[var(--color-accent)] bg-[var(--color-accent-soft)] px-3 py-2 text-sm">
          {message}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="button" variant="secondary" disabled={saving || event.status !== "active"} onClick={() => void update("acknowledge")}>
          Acknowledge
        </Button>
        <Button type="button" disabled={saving || event.status === "resolved"} onClick={() => void update("resolve")}>
          Resolve
        </Button>
      </div>
    </section>
  );
}
