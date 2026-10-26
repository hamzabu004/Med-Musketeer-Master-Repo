import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";

export default defineConfig([
  ...nextVitals,
  globalIgnores([".next/**", ".next-e2e-*/**", "out/**", "build/**", "next-env.d.ts", "playwright-report/**", "test-results/**", "src/api/schema.d.ts", "src/api/openapi.json"]),
]);
