# works-db-and-web

Repository for the construction works database artifacts and MVP web interface.

## Included
- `works-web-mvp/` — FastAPI-based MVP web interface for `works_db_v2`
- `db_schema_rus.md` — Russian description of the database structure
- `db_sample_data.sql` — sample SQL data for reference/testing
- `db_templates_v2/` — import/export templates for the database
- `import_report_to_works_db_v2.py` — report import script
- `export_works_db_v2_to_xlsx.py` — export script for Excel snapshots
- `TASK_import_works_db_v2.md` — task notes for DB import work
- `TASK_web_interface_mvp.md` — task notes for web MVP work

## Safety
This repo must not contain real secrets, live credentials, private memory files, personal notes, or private raw source files that should stay only on the server.

If you clone this repo for deployment, create your own local `.env` files from examples and fill in real values outside git.
