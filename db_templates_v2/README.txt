Шаблоны для БД works_db_v2

Порядок заполнения/импорта:
1. construction_sections
2. construction_section_versions
3. objects
4. object_segments
5. constructive_work_types
6. project_work_items
7. project_work_item_segments
8. daily_reports
9. daily_work_items
10. daily_work_item_segments
11. material_movements
12. stockpiles
13. stockpile_balance_snapshots
14. report_equipment_units
15. work_item_equipment_usage
16. material_movement_equipment_usage

Справочники object_types, constructives, materials, work_types уже живут в БД. В CSV/XLSX на них ссылаемся по *_code.
Формат дат: YYYY-MM-DD.
Пикетаж: numeric(12,2), например 328950.00
Смена: day | night | unknown
