// Saves the cloud API's OpenAPI document as src/api/openapi.json and generates src/api/schema.d.ts
// from it. OPENAPI_SOURCE is a URL or a file path; by default a running API on this machine.
// Plain Node, so it runs on any shell.
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";

const source = process.env.OPENAPI_SOURCE || "http://localhost:8000/openapi.json";
const text = /^https?:\/\//.test(source) ? await (await fetch(source)).text() : readFileSync(source, "utf8");
writeFileSync("src/api/openapi.json", JSON.stringify(JSON.parse(text), null, 1) + "\n");
execFileSync(process.execPath, ["node_modules/openapi-typescript/bin/cli.js", "src/api/openapi.json", "-o", "src/api/schema.d.ts"],
  { stdio: "inherit" });
