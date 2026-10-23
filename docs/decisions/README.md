# Project context and decisions

These files are the single home of the MedMusketeer project context. Earlier copies outside this repository were removed on 2026-10-23; edit only these.

| File | What it holds | Wins on |
|---|---|---|
| `scope.md` | Scope lock: what the project is, committed and excluded scope, roles, research strands, measured results so far, timeline, rules for any session | Scope |
| `stack.md` | Technical decision record: stack, links and authentication, topics, provisioning, IAM, schema summary, envelope, liveness, benchmark design | Implementation detail |
| `mqtt-fixed-path-topics.md` | Fixed-path topics, Mosquitto listeners and ACL files | Detail of `stack.md` |
| `ca-tool-spec.md` | Build spec of the CA and provisioning tool (`tools/ca-tool/`) | Detail of `stack.md` |
| `gaps.md` | What is still undecided or unbuilt, with priorities | — (nothing here is decided) |

The FYP-1 mid report (Chapters 4, 5 and 10) presents the same decisions as requirements and ADR-1 to ADR-8, and holds the full cloud schema. When a decision changes, update the file here and note it for the next report.

Status markers: **Decided**, **Proposed**, **Open**, **Deferred**, **Implemented** (built and tested; evidence in `docs/testing/`).

`scope.md`, `stack.md` and `gaps.md` keep their skill frontmatter (`medmusketeer-fyp`, `medmusketeer-stack`, `medmusketeer-gaps`) so they can also be loaded as Claude skills.
