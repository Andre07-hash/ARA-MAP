# Team A — M1-A hosted integration candidate (in progress)

12 October 2026. Branch `codex/team-a-hosted-integration-v1`, started from
`4670df7348265af66c640069e5ece2a274830fa3` as instructed by
`reports/hosted-transfer-contract-2026-10-12/TEAM_A.md` at supervisor commit
`718f4b76807f745fe5b1088a7950b0fbe090a660`. The branch name is the one that
packet specifies.

**Status: preparation only. Team B's candidate has not been relayed, so
nothing of the transfer protocol or the S3 store is in this tree, and this is
not yet the combined candidate.** No cloud resource, account, credential,
deployment or real data was touched. #29, #28, #30 and C1 are unchanged.

## What is here so far

| Item | State |
|---|---|
| Cloud response guard (`api/index.py`): an answer above 4 MiB is refused with `500 respuesta_demasiado_grande` and logged by size only, instead of being handed to the platform | Implemented, 2 tests |
| Private headers of a binary answer survive the adapter (`private, no-store`, `nosniff`, handler headers) | Tested |
| OIDC handoff cases (token visible to its own request, reset on 401/403/500, absent header, two simultaneous requests) | Written against the frozen interface; **skipped** until `server/almacen_s3.py` exists. The handoff itself is not implemented yet |
| [Operator runbook](OPERATOR_RUNBOOK.md) | Draft; B's verifier usage and store settings are referenced, to be completed from B's candidate |
| [Guía de inicio](GUIA_DE_INICIO.md) (Spanish onboarding) | Draft; file messages to be checked against B's client |

## Still to do, in order

1. Review B's relayed PR at its exact SHA (authorization order, denials before
   store resolution, no provider I/O under a database write lock).
2. Ordinary local merge of that SHA, then #30 at `bc7e421` if not an ancestor.
3. Factory injection and OIDC handoff in `api/index.py`; deferred-error case
   for invalid storage configuration; dependency declaration, cloud lock and
   cloud Python selection.
4. Focused cloud-handler journeys on SQLite and disposable Postgres, affected
   browser journeys, repository checks, exact-head CI.
5. Draft PR against `claude/team-a/application-integration`.

## Verification of this preparation commit

See the commit's CI. Local: `./verificar.sh --todo` (result recorded in the
handback). Nothing here is hosted evidence.
