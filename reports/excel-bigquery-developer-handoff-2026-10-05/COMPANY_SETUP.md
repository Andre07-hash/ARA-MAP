# Company setup inputs

These are missing connection facts, not a request to repeat already settled product decisions. No passwords, private keys or tokens should be pasted into chat or committed to the repository.

| Input | Who supplies it | What the developer needs |
|---|---|---|
| Drive service | Owner or IT | Whether the shared XLSX is in OneDrive/SharePoint, Google Drive, another provider or a local/network drive; choose the first supported provider from this fact |
| Representative workbook | Owner/data employee | Access through the normal sharing flow; exact worksheet/table; representative prices, coordinates, formulas, IDs and expected edits; fictional copy for destructive tests |
| Stable row ID | Data employee + developer | Existing unique company ID, or a one-time permanent ID column and workflow for assigning IDs to new rows |
| Upstream feed | Data employee | Whether employees edit Excel directly or an API/Power Query/system populates it; who refreshes that upstream feed |
| BigQuery target | Company GCP administrator | Project ID, dataset ID, region and separate test destination; dataset should have a named company owner |
| Application access | Company IT/GCP administrator | Approved provider authentication and Google Cloud workload/service identity through secure configuration; test ability to fetch workbook and run required BigQuery jobs/read/write operations |
| Operational hosting | Developer + company IT | Confirm current hosting can run the chosen integration; identify secret storage, account/session store and durable job execution; list any new cost/service before provisioning |

Employees should not need to operate Google Cloud or enter technical settings on each refresh. The developer/IT setup is one-time administration; the recurring user action is saving Excel and clicking Refresh.

While these facts are pending, implement source/repository interfaces, interpretation and ID validation, versioned fixtures, UI states, API contract tests and migration inventories on safe copies. Do not implement several providers speculatively, request broad account credentials or describe real integration as complete before access is tested.
