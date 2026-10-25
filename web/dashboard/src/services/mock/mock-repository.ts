import { browserStorage } from "@/lib/browser-storage";
import type { DemoData } from "@/types";

export class MockRepository {
  read(): DemoData {
    return browserStorage.load();
  }

  update(mutator: (draft: DemoData) => void): DemoData {
    const draft = this.read();
    mutator(draft);
    browserStorage.save(draft);
    return structuredClone(draft);
  }

  reset(): DemoData {
    return browserStorage.reset();
  }
}

export const mockRepository = new MockRepository();
