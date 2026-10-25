// Regenerates src/api/schema.d.ts from the cloud API's OpenAPI document: a URL or a file path in
// OPENAPI_SOURCE, by default a running API on this machine. Plain Node, so it runs on any shell.
import { execFileSync } from "node:child_process";

const source = process.env.OPENAPI_SOURCE || "http://localhost:8000/openapi.json";
execFileSync(process.execPath, ["node_modules/openapi-typescript/bin/cli.js", source, "-o", "src/api/schema.d.ts"],
  { stdio: "inherit" });
