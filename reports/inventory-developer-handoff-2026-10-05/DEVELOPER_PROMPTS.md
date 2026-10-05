# Copy-ready assignments

Use the prompts below with AI developers that have access to `/Users/andrejasso/Desktop/ARA Map`. The packet directory is `/Users/andrejasso/Desktop/ARA Map/reports/inventory-developer-handoff-2026-10-05`. Send the backend and frontend assignments together only after `INTEGRATION_DECISIONS.md` is finalized. Verification can prepare fixtures independently, but must verify the integrated candidate after implementation.

## Backend developer — first implementation assignment

You own backend implementation for ARA Map's shared terrain inventory. Read START_HERE.md, INTEGRATION_DECISIONS.md, BACKEND_PACKET.md and ACCEPTANCE_MATRIX.md in the packet directory. The final integration decisions override provisional alternatives. Inspect the existing application before changing it and preserve all unrelated work.

Implement Stage 1: additive SQLite/PostgreSQL inventory storage, permanent terrain IDs, individual sign-in with exactly one equal team-user type, version-checked draft create/edit, accountable change history and internal record reads. Account provisioning is a setup operation, not a privileged application role. Do not expose open public registration. Use disposable databases and no production credentials. Respect the frozen public/internal contract so later publication and UI work can attach cleanly.

Own server/, api/index.py, necessary scripts/, backend tests and required runtime configuration. Coordinate contracts with the interface developer; do not edit web/ concurrently. Preserve existing imports, USD/MXN behavior and frozen maps. Do not create AI, role hierarchies, shortlist features or a framework rewrite. Deliver BACKEND_RESPONSE.md with changed paths, exact isolated tests/results, schema/recovery effects and unresolved issues. Stop at the stage boundary for supervisor integration review; this is a local development handoff, not permission to deploy or migrate production.

## Interface developer — first implementation assignment

You own ARA Map's interface implementation. Read START_HERE.md, INTEGRATION_DECISIONS.md, FRONTEND_PACKET.md and ACCEPTANCE_MATRIX.md. Preserve the existing Spanish interface, visual style and Leaflet navigation. All signed-in users have identical actions; no roles or approvals.

Begin Stage 1 interface work using fixtures matching the frozen contract while the backend develops. Add explicit public catalog versus signed-in inventory navigation, individual sign-in/session handling, the inventory list/detail and a direct draft editor with validation and recoverable conflicts. Preserve the user's input and viewing context. Do not fetch private datasets during anonymous startup or retain them after logout. Do not fabricate functioning persistence or call a fixture-only demo complete. Integrate with the actual backend when available.

Own web/ and related JavaScript tests; coordinate the contract without editing backend files. Keep authenticated legacy bases, saved maps and comparisons reachable. Supply usable desktop/phone search and filters. Later stages add publication preview/actions, imports/adoption and attention/duplicate review; do not skip ahead into deferred features. Return FRONTEND_RESPONSE.md with changed paths, integrated behavior evidence, relevant tests/screenshots and unverified dependencies. Do not deploy or modify production data.

## Independent verifier — acceptance assignment

You verify the integrated ARA Map candidate independently. Read START_HERE.md, INTEGRATION_DECISIONS.md and ACCEPTANCE_MATRIX.md, then developer responses. Prepare fictional fixtures and disposable databases only. Do not run mutating tests against the default local data or the production URL, and do not infer a passing cloud-auth boundary from the current local server.

Exercise the stage-relevant cases through real APIs and browser flows. Check equal powers across three identities, stale-write protection, draft/public separation, private sentinel non-disclosure through every route including legacy maps/exports, migration preservation/recovery and USD/MXN semantics. For final acceptance, use at least 100 representative records, three sessions and desktop/tablet/phone widths. Report performance observations with their environment and limits, not unsupported capacity claims.

Do not fix implementation code while independently certifying it. File actionable failures with route/action, expected versus actual result, smallest reproduction and evidence location. Return VERIFICATION_RESPONSE.md stating accepted stages, blocked cases, commands, environment, source manifest and what remains unverified. Final production readiness requires the supervisor's integrated review and a reviewed release runbook; passing a local suite alone is insufficient.

## Subsequent assignments

The supervisor issues the next stage using the acceptance report and the actual source state. Each follow-up specifies the concrete behavior, owner, allowed files, dependency and acceptance cases. Routine design choices stay with the team; only unresolved product choices go back to the owner. Do not send the entire future roadmap as an instruction to implement everything at once.
