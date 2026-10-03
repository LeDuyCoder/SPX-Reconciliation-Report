# AI Implementation Prompt — Workspace + Excel Import + SQLite Main Data Explorer

## Role

You are a senior desktop application engineer working inside an existing project.

Your task is to implement the **first core feature** of the application:

> Create and manage workspaces, import an Excel file containing a `Main Data` sheet, validate and persist the imported rows into local SQLite storage, and display the data in a configurable/filterable table.

Do not redesign unrelated parts of the application. Reuse the existing architecture, UI system, state-management pattern, naming conventions, routing, theme, and components wherever possible.

---

# 1. Main Goal

Implement a local-first workspace-based data management feature with this flow:

```text
Create Workspace
      ↓
Open Workspace
      ↓
Import Excel File
      ↓
Find Sheet: "Main Data"
      ↓
Validate Required Columns
      ↓
Preview Import
      ↓
Persist Data into SQLite
      ↓
Display Main Data Table
      ↓
Search / Filter / Sort / Show-Hide Columns
      ↓
Persist Workspace UI Settings
```

The application must continue to work after restart.

All imported data, workspace metadata, and table configuration must be stored locally.

---

# 2. Storage Strategy

Use:

```text
Excel file   = original import source
SQLite       = main local working database
JSON fields  = workspace/table UI configuration
File system  = original imported files, logs, future exports
```

Recommended local structure:

```text
<AppData>/SPXReconciliation/
├── spx_reconciliation.db
├── imports/
│   ├── <workspace-id>/
│   │   └── <original-excel-file>.xlsx
│   └── ...
└── logs/
```

On Windows, prefer an application data directory such as:

```text
C:\Users\<user>\AppData\Roaming\SPXReconciliation\
```

Do not store the database inside `Program Files`.

If the project already has a local application-data path abstraction, reuse it.

---

# 3. Workspace Feature

Implement a workspace management screen.

Each workspace must contain at least:

```text
id
name
description
created_at
updated_at
```

Optional derived information shown in the UI:

```text
total_records
last_imported_at
last_file_name
```

Required actions:

- Create workspace
- Open workspace
- Rename workspace
- Delete workspace
- Show total imported records
- Show created date / last updated date

Deletion must remove the workspace's database records.

If imported Excel source files are stored in the workspace folder, delete those files as well.

Before destructive deletion, show a confirmation dialog.

---

# 4. Workspace Screen

When opening a workspace, provide a screen similar to:

```text
┌──────────────────────────────────────────────────────────────┐
│ Workspace Name                              [Import Excel]   │
│ 12,458 records                                              │
│                                                              │
│ [Search...........................] [Filter] [Columns]       │
│                                                              │
│ Active Filters:                                             │
│ [Status: Received ×] [Station: HCM ×]        [Clear All]   │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│                        MAIN DATA TABLE                       │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│ Showing 1-100 of 12,458                    < 1 2 3 ... >    │
└──────────────────────────────────────────────────────────────┘
```

Keep the design aligned with the existing app style.

Avoid unnecessary dashboard cards, AI-looking decorations, excessive gradients, excessive badges, or visual noise.

This is a data productivity tool, so prioritize:

- readability
- density
- fast interaction
- clear hierarchy
- efficient filtering

---

# 5. Excel Import

Support Excel files:

```text
.xlsx
.xls
```

The selected Excel workbook must contain a sheet named:

```text
Main Data
```

The sheet name must be matched safely.

Preferred behavior:

1. Try exact match: `Main Data`
2. If not found, show the available sheet names
3. Do not silently import another sheet

Error example:

```text
Import failed

Required sheet "Main Data" was not found.

Available sheets:
- Sheet1
- Raw Data
- Summary
```

---

# 6. Expected Main Data Columns

The `Main Data` sheet may contain these columns:

```text
TO Number
TO High Value
SPX Tracking Number
Order High Value
TO Status
High Value
Sender ID
Sender Name
Sender Type
Sender Station Type
Receiver ID
Receiver Name
Receiver type
Receiver Station Type
Current Station
TO Order Quantity
TO Direction
Weight
Length
Width
Height
Line Hual Trip Number
Operator
Create Time
Complete Time
Driver
Driver Scan Time
Journey Type
Remark
Receive Status
TO Remark
Staging Area ID
Exception Tag
Packing Method
Dangerous Goods
```

Important:

The Excel source currently uses:

```text
Line Hual Trip Number
```

Do not automatically rename it to `Line Haul Trip Number` during validation unless the application explicitly implements a column alias system.

Internally, the database field may use:

```text
line_haul_trip_number
```

but the Excel parser must correctly recognize the existing source header.

---

# 7. Header Normalization

When validating headers:

- trim leading/trailing whitespace
- normalize repeated spaces
- handle accidental newline characters
- perform case-insensitive comparison only if safe
- never reorder raw Excel data incorrectly

Example normalization:

```text
" Sender Name "
"Sender   Name"
"Sender Name\n"
```

may resolve to:

```text
Sender Name
```

However, preserve the original header list for diagnostics.

---

# 8. Import Validation

Before inserting data into SQLite, show an import preview.

Example:

```text
Import Main Data

File:
SPX_2026_10_02.xlsx

Sheet:
Main Data ✓

Rows detected:
12,458

Columns detected:
28 / 28

Validation:
✓ All expected columns found

[Cancel]                         [Import Data]
```

If columns are missing:

```text
Columns detected:
26 / 28

Missing columns:
- Exception Tag
- Dangerous Goods
```

Do not crash.

Clearly show:

- missing columns
- unexpected columns
- detected row count
- selected sheet name
- file name

For the first version, allow import if non-critical fields are missing.

Design the validation code so required/optional columns can later be configured.

---

# 9. Database Schema

Use SQLite.

Create migration/version-safe database initialization.

Recommended tables:

## workspaces

```sql
CREATE TABLE workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

## import_files

```sql
CREATE TABLE import_files (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    stored_file_path TEXT,
    sheet_name TEXT NOT NULL,
    row_count INTEGER NOT NULL DEFAULT 0,
    imported_at TEXT NOT NULL,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
);
```

## main_data

```sql
CREATE TABLE main_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    workspace_id TEXT NOT NULL,
    import_file_id TEXT NOT NULL,

    to_number TEXT,
    to_high_value TEXT,
    spx_tracking_number TEXT,
    order_high_value TEXT,
    to_status TEXT,
    high_value TEXT,
    sender_id TEXT,

    sender_name TEXT,
    sender_type TEXT,
    sender_station_type TEXT,

    receiver_id TEXT,
    receiver_name TEXT,
    receiver_type TEXT,
    receiver_station_type TEXT,

    current_station TEXT,

    to_order_quantity REAL,
    to_direction TEXT,

    weight REAL,
    length REAL,
    width REAL,
    height REAL,

    line_haul_trip_number TEXT,

    operator TEXT,

    create_time TEXT,
    complete_time TEXT,

    driver TEXT,
    driver_scan_time TEXT,

    journey_type TEXT,
    remark TEXT,

    receive_status TEXT,
    to_remark TEXT,

    staging_area_id TEXT,
    exception_tag TEXT,
    packing_method TEXT,
    dangerous_goods TEXT,

    FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY (import_file_id) REFERENCES import_files(id) ON DELETE CASCADE
);
```

## workspace_settings

```sql
CREATE TABLE workspace_settings (
    workspace_id TEXT PRIMARY KEY,
    visible_columns_json TEXT,
    column_order_json TEXT,
    column_widths_json TEXT,
    filters_json TEXT,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
);
```

Adjust types to the project's ORM/database abstraction if necessary.

---

# 10. Database Indexes

Add useful indexes for common operations.

At minimum:

```sql
CREATE INDEX idx_main_data_workspace
ON main_data(workspace_id);

CREATE INDEX idx_main_data_receive_status
ON main_data(workspace_id, receive_status);

CREATE INDEX idx_main_data_current_station
ON main_data(workspace_id, current_station);

CREATE INDEX idx_main_data_create_time
ON main_data(workspace_id, create_time);

CREATE INDEX idx_main_data_receiver_id
ON main_data(workspace_id, receiver_id);

CREATE INDEX idx_main_data_trip_number
ON main_data(workspace_id, line_haul_trip_number);
```

Do not create excessive indexes for every column.

---

# 11. Import Transaction

Excel import must be atomic.

Use a database transaction:

```text
BEGIN
    create import_files record
    insert main_data rows
    update import_files.row_count
    update workspace.updated_at
COMMIT
```

If any fatal import error occurs:

```text
ROLLBACK
```

Do not leave a half-imported dataset.

---

# 12. Large File Handling

Do not insert every row one-by-one with a separate transaction.

Use:

- batch insert
- prepared statements
- transaction
- chunk processing if needed

Recommended chunk size:

```text
500 - 2000 rows
```

Do not block the UI thread while parsing or inserting large files.

Show progress:

```text
Reading Excel...
Validating columns...
Importing 3,500 / 12,458 rows...
Finalizing...
```

The user must still receive a clear success/failure result.

---

# 13. Duplicate Import Behavior

For MVP, importing the same file again may create another `import_files` entry.

However, prevent accidental duplicate clicking during an active import.

Disable the import button while processing.

Structure the code so future duplicate detection can use:

```text
file hash
file name
file size
imported timestamp
```

Do not implement complex reconciliation logic yet.

---

# 14. Main Data Table

After successful import, display the records in a desktop-friendly data table.

Required capabilities:

- horizontal scrolling
- sticky/frozen header
- pagination or virtualized loading
- sort ascending/descending
- configurable visible columns
- search
- filter
- reset filters
- row count
- loading state
- empty state
- error state

Do not load all rows into memory if the dataset can become large.

The table should request rows from SQLite using:

```text
LIMIT
OFFSET
WHERE
ORDER BY
```

Example:

```sql
SELECT *
FROM main_data
WHERE workspace_id = ?
ORDER BY create_time DESC
LIMIT 100 OFFSET 0;
```

---

# 15. Pagination

Recommended initial page size:

```text
100 rows
```

Allow:

```text
50
100
250
500
```

Show:

```text
Showing 1-100 of 12,458
```

Do not calculate row positions incorrectly after filtering.

---

# 16. Column Settings

Add a `Columns` button.

Open a dropdown, dialog, or side panel.

Example:

```text
Column Settings

Search columns...

☑ Sender Name
☑ Sender Type
☑ Sender Station Type
☑ Receiver ID
☑ Receiver Name
☐ Receiver Type
☐ Receiver Station Type
☑ Current Station
☑ TO Order Quantity
☑ TO Direction
☑ Weight
☐ Length
☐ Width
☐ Height
...

[Show All]
[Hide All]
[Reset Default]
```

Required behavior:

- show/hide individual columns
- show all
- hide non-essential columns
- reset to default
- persist settings per workspace

Optional if the current table library supports it safely:

- drag reorder
- resize column widths

Persist:

```json
{
  "visibleColumns": [
    "senderName",
    "receiverName",
    "currentStation",
    "toOrderQuantity",
    "weight",
    "receiveStatus"
  ],
  "columnOrder": [
    "senderName",
    "receiverName",
    "currentStation",
    "toOrderQuantity",
    "weight",
    "receiveStatus"
  ],
  "columnWidths": {
    "senderName": 180,
    "receiverName": 200
  }
}
```

---

# 17. Default Visible Columns

Do not show all 28 columns by default because the table will become unreadable.

Recommended defaults:

```text
Sender Name
Receiver ID
Receiver Name
Current Station
TO Order Quantity
TO Direction
Weight
Line Hual Trip Number
Operator
Create Time
Complete Time
Driver
Journey Type
Receive Status
Exception Tag
Dangerous Goods
```

All remaining columns must still be available from `Column Settings`.

---

# 18. Search

Provide a global search box:

```text
Search Main Data...
```

Search primarily across useful text identifiers:

```text
Sender Name
Receiver ID
Receiver Name
Current Station
Line Hual Trip Number
Operator
Driver
Remark
TO Remark
Staging Area ID
```

Prefer SQL search rather than filtering only the currently loaded page.

For SQLite, use parameterized queries.

Never concatenate untrusted search text into raw SQL.

---

# 19. Filtering

Build filters based on field type.

## Text filters

Applicable to:

```text
Sender Name
Receiver Name
Operator
Driver
Current Station
Receiver ID
Staging Area ID
Remark
TO Remark
```

Operators:

```text
contains
equals
starts with
ends with
```

---

## Categorical filters

Applicable to fields such as:

```text
Sender Type
Sender Station Type
Receiver Type
Receiver Station Type
TO Direction
Journey Type
Receive Status
Exception Tag
Packing Method
Dangerous Goods
```

Options must be loaded from the current workspace data.

Example query:

```sql
SELECT DISTINCT receive_status
FROM main_data
WHERE workspace_id = ?
ORDER BY receive_status;
```

Do not hardcode category values.

Allow multi-select where appropriate.

---

## Numeric filters

Applicable to:

```text
TO Order Quantity
Weight
Length
Width
Height
```

Support:

```text
equals
greater than
greater than or equal
less than
less than or equal
between
```

---

## Date filters

Applicable to:

```text
Create Time
Complete Time
Driver Scan Time
```

Support:

```text
from
to
between
```

Parse Excel dates carefully.

Handle both:

- Excel numeric date values
- date/time strings

Do not assume one date format only.

Store normalized ISO-style timestamps where possible.

---

# 20. Active Filter Bar

When filters are applied, show active filter indicators.

Example:

```text
[Receive Status: Received ×]
[Current Station: HCM ×]
[Weight: >= 10 ×]

Clear all
```

Removing a single filter must immediately refresh the table.

`Clear all` must reset all active filters.

---

# 21. Sorting

Clicking a sortable column header should cycle through:

```text
none
ascending
descending
```

Only one sort column is required for MVP.

Structure the query builder so multi-column sorting can be added later.

Whitelist valid sortable columns.

Never accept arbitrary column names directly into raw SQL.

---

# 22. Query Layer

Create a clean repository/query abstraction.

Example conceptual API:

```text
getWorkspaceRows(
    workspaceId,
    page,
    pageSize,
    search,
    filters,
    sort
)

getWorkspaceRowCount(
    workspaceId,
    search,
    filters
)

getDistinctColumnValues(
    workspaceId,
    column
)
```

Do not scatter SQL query construction throughout UI components.

Keep:

```text
UI
↓
state/controller/bloc/viewmodel
↓
repository/service
↓
SQLite datasource
```

Follow the architecture already used by the project.

---

# 23. Workspace Persistence

When closing and reopening the app:

- workspaces must remain
- imported data must remain
- workspace row counts must remain
- visible columns must remain
- column order must remain
- column widths should remain if supported
- latest table settings should be restored

Do not require the user to re-import Excel every time.

---

# 24. Import Source Preservation

After a successful import, optionally copy the source Excel file into:

```text
imports/<workspace-id>/
```

Store the resulting path in:

```text
import_files.stored_file_path
```

Use a unique name if a file with the same name already exists.

Example:

```text
20261002_213000_SPX_Report.xlsx
```

Failure to preserve the original source file should not corrupt already-imported database rows.

---

# 25. Error Handling

Handle at minimum:

```text
File cannot be opened
Unsupported Excel format
Main Data sheet missing
Empty Main Data sheet
Header row missing
Duplicate headers
Missing expected columns
Invalid numeric cell
Invalid date cell
SQLite insert failure
Disk write failure
Permission failure
Cancelled import
```

Do not crash the application.

Show concise user-facing messages and write technical details to logs if the project supports logging.

---

# 26. Data Parsing Rules

Use safe conversion.

Examples:

## Empty values

Excel values such as:

```text
""
null
"N/A"
```

should not blindly become numeric zero.

Prefer `NULL` where appropriate.

## Numeric values

Fields:

```text
TO Order Quantity
Weight
Length
Width
Height
```

should be parsed numerically when valid.

If parsing fails:

- store `NULL`
- record a warning count if practical
- do not fail the entire import unless strict validation is enabled

## Text identifiers

Do not convert IDs into numbers if doing so may remove leading zeros.

Especially:

```text
Receiver ID
Staging Area ID
Line Hual Trip Number
```

Keep them as strings.

---

# 27. Import Result

After a successful import, show a clear result:

```text
Import completed

File:
SPX_2026_10_02.xlsx

Imported:
12,458 rows

Skipped:
0 rows

Warnings:
3 cells could not be parsed as numeric values

[View Main Data]
```

Avoid excessive modal interruptions.

---

# 28. Empty Workspace State

A workspace with no imported data should display:

```text
No Main Data yet

Import an Excel file containing the
"Main Data" sheet to get started.

[Import Excel]
```

Do not show an empty giant table before the first import.

---

# 29. Performance Requirements

Target reasonable usability for:

```text
10,000 rows
50,000 rows
100,000+ rows
```

Avoid:

```text
SELECT * without LIMIT for normal table rendering
loading all rows into UI memory
filtering only the current page
executing one SQLite transaction per row
rebuilding the entire table unnecessarily
```

Use lazy loading/pagination.

---

# 30. UI State

Implement clear states for:

```text
initial
loading
empty
importing
loaded
filtering
error
```

Avoid mixing database logic directly into widgets/components.

---

# 31. Flutter Windows Notes

If this project is Flutter Desktop / Windows, prefer technologies already present in the project.

If SQLite has not yet been implemented, consider:

```text
drift + sqlite3
```

or:

```text
sqflite_common_ffi
```

Choose one based on the current codebase.

Do not introduce both.

For file selection, use the project's existing file picker package if available.

For application data directories, use the current platform path abstraction, commonly:

```text
path_provider
```

For heavy Excel parsing, consider an isolate/background worker where appropriate.

Do not freeze the Flutter UI thread during large imports.

---

# 32. Suggested Internal Models

Conceptual models:

```text
Workspace
ImportFile
MainDataRow
WorkspaceTableSettings
TableFilter
TableSort
PagedResult<T>
ImportPreview
ImportResult
ImportWarning
```

Do not expose database rows directly to the UI if the project uses domain models.

---

# 33. Recommended Module Structure

Adapt this to the existing project.

Example:

```text
features/
└── workspace/
    ├── data/
    │   ├── local/
    │   │   ├── workspace_database.*
    │   │   └── workspace_dao.*
    │   ├── models/
    │   └── repositories/
    │
    ├── domain/
    │   ├── entities/
    │   ├── repositories/
    │   └── usecases/
    │
    └── presentation/
        ├── workspace_list/
        ├── workspace_detail/
        ├── import_excel/
        └── main_data_table/
```

Do not force Clean Architecture if the existing project uses another pattern.

Stay consistent with the current project.

---

# 34. Implementation Order

Implement in this order:

## Phase 1 — Local Persistence

- SQLite initialization
- schema versioning
- workspace CRUD
- import_files table
- main_data table
- workspace_settings table

## Phase 2 — Workspace UI

- workspace list
- create workspace
- delete workspace
- workspace detail empty state

## Phase 3 — Excel Import

- file picker
- workbook parsing
- `Main Data` detection
- header normalization
- column validation
- import preview
- transaction-based batch insertion
- progress state

## Phase 4 — Data Table

- SQLite pagination
- row count
- render table
- sorting
- loading/empty/error states

## Phase 5 — Filtering

- global search
- text filters
- categorical filters
- numeric filters
- date filters
- active filter bar
- clear/reset

## Phase 6 — Column Settings

- visible columns
- show/hide
- reset defaults
- persistence per workspace
- reorder/resize if supported

---

# 35. Do Not Implement Yet

Do NOT implement these features as part of this task unless the current app already requires them:

```text
reconciliation engine
automatic matching
analytics dashboard
charts
AI analysis
cloud sync
user authentication
multi-user collaboration
online database
PDF reporting
complex export templates
exception scoring
business-rule engine
```

Keep this first core module stable and extensible.

---

# 36. Acceptance Criteria

The feature is considered complete when all of the following are true:

- A user can create a workspace.
- Workspaces remain after restarting the application.
- A user can select an Excel file.
- The app specifically reads the `Main Data` sheet.
- The app validates the expected columns.
- The app previews the import before saving.
- Imported rows are persisted in SQLite.
- Imported records remain after restarting the app.
- The table does not require re-reading Excel every time.
- The table supports pagination.
- The table supports sorting.
- The table supports global search.
- The table supports filters.
- Filters query the entire workspace dataset, not only the visible page.
- Columns can be shown/hidden.
- Column visibility is persisted per workspace.
- The UI stays responsive during large imports.
- Failed imports do not leave partial rows.
- Workspace deletion cleans up associated data.
- SQL queries are parameterized.
- The implementation follows the existing project architecture and style.

---

# 37. Code Quality Requirements

Before finishing:

1. Scan the current codebase first.
2. Reuse existing components and utilities.
3. Avoid duplicate services.
4. Avoid giant files.
5. Separate UI, state, parsing, and persistence responsibilities.
6. Use descriptive names.
7. Add comments only where logic is genuinely non-obvious.
8. Remove debug prints.
9. Handle nullable Excel values safely.
10. Ensure database resources are disposed correctly.
11. Test app restart persistence.
12. Test import of at least one large dataset.
13. Test missing-sheet behavior.
14. Test missing-column behavior.
15. Test workspace deletion.
16. Test filter + pagination + sorting together.

---

# 38. Final Delivery

After implementation, provide a concise development summary containing:

```text
1. Files created
2. Files modified
3. SQLite schema added
4. Excel parsing approach
5. Workspace flow
6. Table/filter implementation
7. Important architectural decisions
8. Known limitations
9. Manual test steps
```

Also explicitly state whether:

```text
- data survives app restart
- large imports are processed off the UI thread
- queries use SQLite pagination
- filters operate on the full dataset
- source Excel files are preserved locally
```

Do not claim success for anything that has not actually been implemented or tested.
