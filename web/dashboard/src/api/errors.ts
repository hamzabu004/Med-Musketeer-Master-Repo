/** An error answer from the API, or no answer at all (status 0). */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    /** The response's `detail`, as sent: a string, an object, or FastAPI's validation list. */
    readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** The message in a FastAPI error body. `detail` is a string (HTTPException), an object such as
 * {error, constraint} (a database rule), or a list of validation errors (422). */
export function detailMessage(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (!item || typeof item !== "object") return null;
        const { loc, msg } = item as { loc?: unknown[]; msg?: string };
        const field = Array.isArray(loc) ? loc.filter((part) => part !== "body").join(".") : "";
        return msg ? (field ? `${field}: ${msg}` : msg) : null;
      })
      .filter(Boolean);
    return messages.length ? messages.join("; ") : null;
  }
  if (detail && typeof detail === "object" && "error" in detail) return String((detail as { error: unknown }).error);
  return null;
}

export async function errorFromResponse(response: Response): Promise<ApiError> {
  let detail: unknown;
  try {
    detail = ((await response.json()) as { detail?: unknown }).detail;
  } catch {
    detail = undefined;
  }
  return new ApiError(response.status, detailMessage(detail) || response.statusText || `HTTP ${response.status}`, detail);
}

/** What a database rule the API reports as {error, constraint} means for the user
 * (constraint names from cloud/backend/migrations/versions/0001_initial_schema.py). */
const CONSTRAINTS: Record<string, string> = {
  devices_pkey: "A device with this id is already registered.",
  device_credentials_auth_method_credential_ref_key: "This certificate is already registered, possibly for another device.",
  device_grants_one_open: "The device is already granted to an organisation. End that grant first.",
  device_assignments_one_active_per_device: "This wearable is already issued to a patient.",
  device_assignments_one_active_per_patient: "This patient already has a wearable. Return it first.",
  patient_disorders_pkey: "This disorder is already recorded for the patient.",
  patients_org_id_pseudonym_key: "This pseudonym is already used in the organisation.",
  care_assignments_one_active: "The patient's doctor changed at the same time. Reload and try again.",
};

function constraintMessage(detail: unknown): string | null {
  if (detail && typeof detail === "object" && "constraint" in detail) {
    return CONSTRAINTS[String((detail as { constraint: unknown }).constraint)] ?? null;
  }
  return null;
}

/** What to tell the user. The API answers 404 both for something that does not exist and for
 * something outside the caller's reach (D9), so the message does not claim which. */
export function userMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "Something went wrong.";
  switch (error.status) {
    case 0:
      return "The server could not be reached. Check your connection and try again.";
    case 401:
      return "Your session has ended. Sign in again.";
    case 403:
      return "Your role does not allow this.";
    case 404:
      return "Not found, or not available to you.";
    case 409:
    case 422:
      return constraintMessage(error.detail) ?? error.message;
    case 502:
    case 503:
      return "A service the server depends on is unavailable. Try again shortly.";
    default:
      return error.status >= 500 ? "The server had a problem. Try again shortly." : error.message;
  }
}
