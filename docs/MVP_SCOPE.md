# MVP scope

P0 implemented: web/API, local credentials and scoped sessions, SQLite migrations, durable jobs and worker leases, executive instruction → typed proposal → approval → local tasks, job/history polling, status updates, versioned sources, Qdrant ACL retrieval, five Decimal financial metrics with lineage, on-demand briefing, safe audit, demo/Ollama/compatible HTTP providers, bilingual UI and partner materials.

The customer demonstration increment adds three connected capabilities:

- Text PDF and DOCX (including tables), alongside TXT/Markdown: byte-preserved originals, immutable extracted text, page/paragraph/table-row anchors, isolated bounded parsing and current ACL checks on historical downloads. OCR is separate and unavailable.
- Excel/CSV catalog → reviewed line items → versioned RUB quote with Decimal discounts/VAT, formula and source-row evidence → DOCX/PDF export → hash-bound approval and one local assigned task. Price formulas in Excel are rejected. The model does not set prices or execute actions.
- Personal task assignees, My/Today/Overdue/Blocked views, timezone-aware deadlines, complete SQL counters and factual task links in the on-demand briefing. Existing unassigned tasks remain valid; assigned employee updates require the assignee, while team visibility is retained.

Constraints: Chief of Staff demo plans only its supported procurement scenario; structured assignment fields are explicitly confirmed. Demo quote suggestions only match explicit SKU × quantity and require review. Uploaded files are user data; seeded financial records remain synthetic even with real generation. No supplier messages or scheduled notifications are sent. No mail/CRM/accounting connector exists. The local users are still the seeded owner/manager/employee accounts; user administration and empty-customer provisioning are not delivered.

Retrieval uses dense/hash-based indexing without a hybrid index or reranker. Owner CLI reindex may need explicit source ACL grants and a maintenance window. PDF parsing is not OCR or an OS sandbox. Read DEPENDENCY_REVIEW before a real-data pilot. Hardware runtime is not installed or verified.

The API/UI capability matrix separates implementation, historical validation, runtime mode and hardware evidence. Remaining P1/P2 scope must not be described as delivered.
