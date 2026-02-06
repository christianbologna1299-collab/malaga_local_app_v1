\# Banker Analytics — Engineering Policy (Bank-Grade)



This project is built to be \*\*trustworthy, reproducible, and safe\*\* for real banking workflows.

We prioritize: \*\*correctness > auditability > reliability > speed > new features\*\*.



---



\## 0) Core Principles (Non-Negotiable)

\- \*\*Deterministic-first:\*\* Same inputs must produce the same outputs.

\- \*\*Single Source of Truth:\*\* No duplicate business logic.

\- \*\*Hard user isolation:\*\* user\_id boundary is enforced everywhere.

\- \*\*Safe-fail by design:\*\* failures degrade gracefully; no silent corruption.

\- \*\*Auditability:\*\* every artifact must be defendable (what data, when, how, which version).

\- \*\*Local-first:\*\* works on Windows, no Docker required, no cloud dependency required.



---



\## 1) Architecture Rules (No Spaghetti)

\### Layering

\- \*\*Routes (FastAPI):\*\* auth checks + input parsing + response rendering only

\- \*\*Services:\*\* orchestration (load analysis file, call compute functions, store results)

\- \*\*Domain modules:\*\* pure deterministic computations (KPIs, flags, shocks, trends)

\- \*\*Repositories/DB layer:\*\* CRUD only (no business logic)

\- \*\*Templates:\*\* presentation only (no calculations besides formatting)



\*\*Rule:\*\* Computation must not depend on HTTP request objects, templates, or global state.



---



\## 2) Single Source of Truth (Anti-Redundancy)

\- Each concept (KPIs, flags, shocks, trends) has \*\*one canonical implementation\*\*.

\- No “just this once” copies of formulas.

\- No duplicate parsing, hashing, validation functions across modules.



\*\*Rule:\*\* If the same math exists twice, it is a bug and must be refactored.



---



\## 3) Determinism \& Reproducibility

\### Inputs and caching

\- Raw datasets are stored on disk (parquet preferred).

\- DB stores only metadata + derived summaries (no DataFrame storage in JSON).

\- Every derived output stores:

&nbsp; - `analysis\_id`

&nbsp; - `user\_id`

&nbsp; - `computed\_at`

&nbsp; - `engine\_version` (e.g. KPI\_ENGINE\_VERSION, TREND\_ENGINE\_VERSION)

&nbsp; - `inputs\_hash` (analysis file hash + parameters + engine version)



\*\*Rule:\*\* If we cannot reproduce output tomorrow, it does not ship.



---



\## 4) Security (Hard Isolation)

\### Ownership checks required everywhere

Any access to:

\- `analysis\_id`

\- `scenario\_id`

\- `export\_id`

\- stored files



must verify:

\- authenticated user exists

\- record `user\_id` matches session `user\_id`



\*\*Rule:\*\* “No ownership check, no merge.”



\### Auth/session rules

\- Password hashing: `passlib\[bcrypt]`

\- Session: signed cookie middleware

\- Logout clears session

\- Sensitive routes redirect to `/login` (HTML) or return `401/403` (API)



---



\## 5) Data Handling Rules

\- Parse → validate → clean → store cleaned dataset to disk

\- Store safe filename (sanitized, normalized)

\- Never trust user-supplied paths

\- Never store DataFrames in DB JSON

\- File storage is immutable: do not overwrite old analyses



\*\*Rule:\*\* Files are immutable; derived results are versioned and hashed.



---



\## 6) Safe-Fail \& Containment (Reliability)

Failures must be:

\- visible to the user (clear message)

\- logged with request\_id + user\_id + analysis\_id (when applicable)

\- contained (no partial writes that corrupt state)

\- recoverable (user can retry later)



Examples:

\- Trend compute fails → analysis still saved; trends marked unavailable

\- PDF export fails → scenario may still exist; export record not created

\- Cleanup never deletes referenced exports



\*\*Rule:\*\* Failure must not destroy history or trust.



---



\## 7) Export Retention \& Cleanup Rules

\- \*\*Never delete any file referenced in DB.\*\*

\- Cleanup may delete only \*\*orphan\*\* files not referenced by exports table.



\*\*Rule:\*\* “DB reference beats filesystem cleanup.”



---



\## 8) Migrations Discipline

\- All schema changes require a migration:

&nbsp; - `migrations/000X\_description.sql`

\- App startup applies pending migrations in order.

\- No manual edits to production DB files.



\*\*Rule:\*\* Schema changes are controlled, reviewable, and reversible.



---



\## 9) Logging \& Traceability

Every request should log:

\- request\_id

\- route name

\- user\_id (safe to log)

\- analysis\_id/scenario\_id/export\_id when applicable

\- duration

\- errors with stack trace



\*\*Rule:\*\* If a banker asks “what happened,” we can answer.



---



\## 10) Testing Gates (Must Always Pass)

Minimum integration tests required:

\- Register/login/logout

\- Upload → analysis saved → reopen later

\- User A cannot access User B analyses/exports (404/403)

\- Export PDF works for historical analysis\_id

\- Cleanup does not delete referenced exports

\- Filename sanitization prevents path traversal

\- Determinism: same analysis\_id regenerates same KPI/flag structure (within rounding)



\*\*Rule:\*\* If workflow tests fail, nothing merges.



---



\## 11) Artifact Metadata (Bank Trust)

Every generated PDF/Excel includes footer metadata:

\- analysis\_id

\- report\_kind

\- template\_version

\- computed\_at

\- data “as-of” range

\- optional: file\_hash



\*\*Rule:\*\* Every artifact can defend itself.



---



\## 12) Release, Rollback, and Backup Policy

\### Backups (local-first)

Daily backups (minimum):

\- `banker\_analytics.db`

\- `data/analyses/`

\- `exports/`



Stored as:

\- `backups/YYYY-MM-DD/`



\### Rollback plan

\- Tag releases in git (e.g., `v0.3.0`)

\- If a release breaks:

&nbsp; - revert to last tagged version

&nbsp; - keep DB + files unchanged

&nbsp; - restore DB from backup only if corruption is confirmed



\*\*Rule:\*\* If something breaks, we can restore within 10 minutes.



---



\## 13) AI Readiness Rules (Future)

AI (Claude/other) is:

\- a writer + explainer + validator

\- \*\*never\*\* source of truth



AI may only use:

\- computed KPIs/flags/trends/scenario summaries

\- fetched data that is cached with timestamps + sources

\- explicit user-defined policy thresholds



AI must never:

\- invent numbers

\- approve/deny credit

\- overwrite history

\- change assumptions silently



\*\*Rule:\*\* AI can write, but it cannot decide or fabricate.



