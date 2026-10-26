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

/** Classification labels: AAMI beat classes from the gateway/cloud model, or the wearable's binary
 * screen. Other labels are shown as sent. */
const BEAT_CLASSES: Record<string, string> = {
  N: "Normal beat (N)",
  S: "Supraventricular ectopic (S)",
  V: "Ventricular ectopic (V)",
  F: "Fusion beat (F)",
  Q: "Unclassifiable (Q)",
  normal: "Normal (screen)",
  abnormal: "Abnormal (screen)",
};

export function beatLabel(label: string | null | undefined): string {
  if (!label) return "Not classified";
  return BEAT_CLASSES[label] ?? label;
}

export function confidence(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`;
}
