# Team B — attachments and KMZ geography

Obtain these instructions from GitHub at the supervisor's named commit; see [GITHUB_HANDOFF.md](GITHUB_HANDOFF.md). Do not rely on desktop paths or assume this packet is already in main.

Read [MASTER_PLAN.md](MASTER_PLAN.md) and [TWO_TEAM_DELIVERY_PLAN.md](TWO_TEAM_DELIVERY_PLAN.md). Record their exact published instruction commit in your response. The owner has paused connected Excel; preserve that work and do not resume its previous assignment.

Your feature ownership: attachment service/UI, private file storage integration, PDF opening/downloading, KMZ parsing and layout display, geometry versions, and the existing map renderer's KMZ extension. You own both frontend and backend for this feature. Team A integrates shared schemas, roles, routes, grid slots, and the application shell.

**First assignment — investigate files and geometry while Team A prepares the master table:**

1. Review the current Leaflet renderer, terrain identity/selection, X/Y behavior, and saved-map snapshots. Propose the smallest extension for boundaries; do not replace or reimplement the established X/Y workflow.
2. Investigate representative KMZ files when available, otherwise use explicitly fictional fixtures. Establish how polygons, multipart terrain, holes, ambiguous layouts, and unsupported contents will be handled. A bounded, isolated parsing/rendering experiment may support the report; do not present synthetic success as real-file acceptance.
3. Draft the attachment and geometry contract with examples: terrain/column ID, file/version ID, processing states, active/last-valid geometry, bounds, replacement/removal, authorized access, and snapshot retention. A valid boundary must locate a terrain with blank X/Y.
4. Propose upload-cell and file-detail widgets with clear inputs/callbacks so A can embed them. Design against shared examples, not private assumptions about the unfinished grid.
5. Recommend durable private storage/upload options after checking the existing hosting constraints and likely file sizes. Identify the operator action needed later. Do not provision services, change credentials, or assume permanent storage on a function's local disk.
6. Propose small PRs and tests. Send A a precise list of schema, permission, route, and shared-client changes. Keep your implementation in owned modules; do not edit the shared migration version in parallel.

Deliver a concise report containing feasibility findings, draft contract/examples, widget boundaries, storage recommendation and unresolved inputs, shared-file requests, and first PR sequence. Distinguish ready local work from cloud-access dependencies.

After the supervisor consolidates the shared contract, implement the bounded Team B packet using fictional terrain fixtures as needed. Replace mocks with real integration as soon as A's shared prerequisites land. Mock-only uploads or polygons are not acceptance of persistent attachments or the hosted employee workflow.

Follow the delivery plan's ownership rules and handoff format. Do not edit A's active grid/auth/schema files, silently select an arbitrary polygon, publish file URLs, or alter production as part of this preparation.
