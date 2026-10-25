/** Display labels for the API's codes. Unknown codes are shown as sent, made readable. */
export function labelize(value: string | null | undefined): string {
  if (!value) return "—";
  if (NAMES[value]) return NAMES[value];
  const text = value.replaceAll("_", " ").replaceAll(".", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const NAMES: Record<string, string> = {
  dos_flood: "DoS flood",
  syn_flood: "SYN flood",
  mqtt_flood: "MQTT flood",
  arp_spoof: "ARP spoofing",
  port_scan: "Port scan",
  no_threat: "No threat",
  x509_mtls: "Certificate (mTLS)",
};

export const deviceTypeLabels: Record<string, string> = { wearable: "Wearable", fixed_gateway: "Fixed gateway" };

export function deviceType(value: string): string {
  return deviceTypeLabels[value] ?? labelize(value);
}

/** The first block of a UUID, enough to tell records apart on screen; the full id is in the title. */
export function shortId(id: string | null | undefined): string {
  return id ? id.split("-")[0] : "—";
}
