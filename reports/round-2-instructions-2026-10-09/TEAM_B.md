# Team B — packet 2B: attachment HTTP and bounded geometry delivery

Both of your Round 1 handbacks are accepted in their stated scopes. Preserve
#21 and #23; do not continue research or integrate E5. Start the separate
`claude/team-b/attachment-http` branch using START_HERE.md's immediate-start
protocol. No dependency on A's grid or custom-column implementation.

## 1. Thin authenticated transport over the accepted lifecycle

Read the lifecycle report plus `CORRECTIONS_2026-10-09.md` at accepted #23;
the corrected signatures supersede the initial report. Implement
`server/api/archivos.py` and dedicated geometry handlers/read support, keeping
SQL in `server/repo/`. Reuse `server/archivos.py` for lifecycle operations;
do not implement a second state machine or weaken its guards.

Cover start, raw content staging, complete/replay, cancel, reprocess/candidate
selection, retained-version activation, retirement, paged list/history,
authorized finalized-version download and geometry delivery. Document exact
method/path/capability/body/result/error for every handler in API_CONTRACT.md.
Follow INTERFACES.md for geometry limits and future widget handoff.

Use the existing `Request.sesion`, P2 capabilities, real current terrain
ownership and accepted lifecycle final rechecks. No client actor/base override.
Apply the L1 non-disclosure rule to every new version/geometry/download path,
including missing IDs with expired/revoked sessions. A real session/capability
failure remains 401/403 before resource absence can reveal anything. Scope
each geometry independently; an authorized terrain parameter is not proof
that a supplied version/geometry belongs to it. No serialized session reference.

Keep accepted field names, idempotency/revision semantics, deadlines, lease
results, cleanup truthfulness and privacy. `listar` returns
`{archivos, cursor_siguiente}`, default 50/max 100; history retains bounded
paging and redacted `privado` events. Map known validation/state/busy/storage
failures to controlled statuses/codes; do not catch arbitrary defects as 422.
Keep retries explicit and safe; an ambiguous completion is resolved by replay,
not a new version or deletion of possibly committed bytes.

## 2. Content and downloads — local/fake, not hosted

Use the accepted local/fake store through an injected, documented provider
factory. No provider SDK, signed credentials or public download URL. Keys
remain internal. Reads/downloads select exact immutable finalized versions;
retired-but-retained finalized content remains available only under current
terrain authorization. Never serve staging, another account's pending content,
failed/unverified bytes, arbitrary filesystem paths or a mutable current
pointer under an immutable version URL.

Stage a raw PDF/KMZ request (not multipart/base64 with uncertain overhead),
enforce actual and declared size/type/hash, PDF <=25 MiB and KMZ <=20 MiB.
Preserve parser limits and global MAX_BODY. The current dispatcher already
buffers a body up to 25 MiB before constructing Request: **do not claim
end-to-end streaming**, and do not rewrite it in B's branch. Feed the store
bounded chunks and report the real local peak allocation. Hosted upload
transport is a later packet; this local path is not a Vercel size guarantee.

Downloads need correct content type, sanitized Content-Disposition (including
Unicode/quotes/CRLF cases), `nosniff` and private `no-store`. Choose safe
attachment download by default; do not invent an HTML viewer. Reauthorize on
every new request, including conditional/range requests if supported. No new
read credentials are needed: the old 60-second future grant policy stays
reserved for cloud work. Already delivered bytes cannot be recalled.

## 3. Route ownership and honest HTTP evidence

`server/app.py`, `server/router.py`, auth and shared configuration remain
A-owned. Ordinary route/transport mounting is reserved for **3A**. Publish
the exact registry entries and any minimal typed binary-response/provider
injection changes needed in `INTEGRATION_REQUESTS.md`; include method, handler,
capability, headers/status/body contract and applicable tests. The current
tuple response is XLSX-specific: do not disguise PDFs as spreadsheet downloads
or globally change its meaning.

For 2B tests, temporarily register your routes with their real capabilities in
an isolated fixture around the existing dispatcher and real cookie sessions.
If a binary response adapter is needed, keep the thin adapter in the test
harness and spell out its future A-owned production equivalent. Do not replace
authentication, scope helpers, lifecycle, SQL or storage with an alternate fake
HTTP implementation. Test JSON routes through the actual dispatcher and binary
handlers plus the declared adapter through an actual loopback HTTP connection.
Restore registration/patches between tests. Clearly label this as **HTTP
harness evidence, not application-mounted endpoint acceptance**.

No production registration patch is required to finish 2B. If you uncover a
security/transaction defect in shared code, provide the failing case and a
precise request for A/supervision, and continue unaffected work. Do not bypass
the guard in a test to achieve green results.

## 4. Acceptance

- Real-session HTTP matrix on SQLite and disposable Postgres: no grant,
  assigned/multiple bases, admins, archived terrain/base, stale/revoked/logout/
  expired sessions, role/account changes, guessed cross-resource IDs and mixed
  authorized/missing/out-of-scope geometry batches. Identical non-disclosing
  unavailable results; no metadata, key or private pending-event leaks.
- Real PDF and KMZ round trip via start/content/complete, single-candidate and
  explicit multi-candidate selection/activation, download/hash identity,
  retained-version activation, retry, cancel, retire and authorized replay.
  Preserve old active layout on failed/stale replacement and terrain version
  independence. Include size equality/+1, wrong hash/signature, malformed
  bodies/cursors and disconnected or truncated uploads where the local harness
  can exercise them; document remaining dispatcher limitations.
- Both race orders at request/finalization boundaries versus scope loss and
  cancellation/retirement; errors must not leave unauthorized terminal writes.
  Reuse the accepted deterministic lifecycle tests, adding actual HTTP cases
  rather than duplicating every old matrix. Busy is controlled, never auto-retry.
- Geometry: all INTERFACES.md cases, especially full-limit data, exact chunk
  reassembly/hash, holes/multipart, byte-boundary/UTF-8 handling, invalid offsets,
  forged IDs, last chunk, replacement/retirement between chunks and revocation
  before the next chunk. No truncated object presented as a complete geometry.
- Record response bytes, bounded query/body loading and peak allocation on
  near-limit PDF/KMZ/geometry inputs. Full combined suites, Python 3.9, JS,
  applicable lint/types and exact-head CI at handback. No renderer matrix rerun
  is requested because no renderer change is assigned.

Report: `reports/team-b-attachment-http-2026-10-09/START_HERE.md`, with
API_CONTRACT.md, INTEGRATION_REQUESTS.md, examples, evidence and remaining 3A/3B
mounting/client work. Separate draft PR; exact source/checkpoint/code/final
heads. Stop; no 3B, main merge, deployment or research extension.
