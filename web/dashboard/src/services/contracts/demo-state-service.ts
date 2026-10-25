import type { DemoData } from "@/types";

export interface DemoStateService {
  resetDemoData(): Promise<DemoData>;
}
