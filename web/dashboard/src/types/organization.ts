export interface Organization {
  id: string;
  name: string;
  code?: string;
  status: "active" | "disabled";
  createdAt?: string;
}
