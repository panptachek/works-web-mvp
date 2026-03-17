-- Тестовые примеры данных для works_db
-- ВНИМАНИЕ: это демонстрационные данные. Применять только после отдельного подтверждения.

begin;

-- 1. Участки
insert into construction_sections (code, name, is_active)
values
  ('UCH_1', 'Участок 1', true),
  ('UCH_2', 'Участок 2', true),
  ('UCH_3', 'Участок 3', true)
on conflict (code) do nothing;

-- 2. Границы участков
insert into section_boundary_versions (
  section_id, valid_from, valid_to, pk_start_text, pk_end_text, pk_start_m, pk_end_m, is_current, note
)
select s.id, v.valid_from, null, v.pk_start_text, v.pk_end_text, v.pk_start_m, v.pk_end_m, true, v.note
from (
  values
    ('UCH_1', date '2026-03-14', 'ПК2878+00', 'ПК2951+00', 287800, 295100, 'Граница участка 1'),
    ('UCH_2', date '2026-03-14', 'ПК2952+00', 'ПК3020+00', 295200, 302000, 'Граница участка 2'),
    ('UCH_3', date '2026-03-14', 'ПК3021+00', 'ПК3100+00', 302100, 310000, 'Граница участка 3')
) as v(section_code, valid_from, pk_start_text, pk_end_text, pk_start_m, pk_end_m, note)
join construction_sections s on s.code = v.section_code;

-- 3. Дороги
insert into roads (code, name, road_type, is_active)
values
  ('ROAD_MAIN_TRACK', 'Основной ход / земляное полотно', 'main_track', true),
  ('ROAD_TEMP_7', 'Притрассовая а/д №7', 'temporary_access_road', true),
  ('ROAD_TECH_A', 'Технологический проезд А', 'temporary_access_road', true),
  ('ROAD_SITE_1', 'Технологическая площадка 1', 'temporary_access_road', true)
on conflict (code) do nothing;

-- 4. Сегменты дорог
insert into road_segments (road_id, pk_start_m, pk_end_m, pk_start_text, pk_end_text, note)
select r.id, v.pk_start_m, v.pk_end_m, v.pk_start_text, v.pk_end_text, v.note
from (
  values
    ('ROAD_MAIN_TRACK', 287800, 295100, 'ПК2878+00', 'ПК2951+00', 'Основной ход в границах уч.1'),
    ('ROAD_TEMP_7', 290000, 291500, 'ПК2900+00', 'ПК2915+00', 'Временная дорога №7'),
    ('ROAD_TECH_A', 295200, 296000, 'ПК2952+00', 'ПК2960+00', 'Технологический проезд')
) as v(road_code, pk_start_m, pk_end_m, pk_start_text, pk_end_text, note)
join roads r on r.code = v.road_code;

-- 5. Ответственность участков за дороги
insert into section_road_responsibility (
  section_id, road_id, valid_from, valid_to, pk_start_m, pk_end_m, pk_start_text, pk_end_text, note
)
select s.id, r.id, v.valid_from, null, v.pk_start_m, v.pk_end_m, v.pk_start_text, v.pk_end_text, v.note
from (
  values
    ('UCH_1', 'ROAD_MAIN_TRACK', date '2026-03-14', 287800, 295100, 'ПК2878+00', 'ПК2951+00', 'Ответственность участка 1'),
    ('UCH_2', 'ROAD_TECH_A', date '2026-03-14', 295200, 296000, 'ПК2952+00', 'ПК2960+00', 'Ответственность участка 2'),
    ('UCH_1', 'ROAD_TEMP_7', date '2026-03-14', 290000, 291500, 'ПК2900+00', 'ПК2915+00', 'Подъездная дорога участка 1')
) as v(section_code, road_code, valid_from, pk_start_m, pk_end_m, pk_start_text, pk_end_text, note)
join construction_sections s on s.code = v.section_code
join roads r on r.code = v.road_code;

-- 6. Конструктивы
insert into constructives (code, name, sort_order, is_active)
values
  ('POH', 'Основной ход', 10, true),
  ('VPD', 'Временные подъездные дороги', 20, true)
on conflict (code) do nothing;

-- 7. Виды работ
insert into work_types (constructive_id, code, name, unit, report_group, sort_order, is_ambiguous, is_active)
select c.id, v.code, v.name, v.unit, v.report_group, v.sort_order, false, true
from (
  values
    ('POH', 'CUT_SOIL', 'Разработка грунта', 'м3', 'Земляные работы', 10),
    ('POH', 'SOIL_REPLACEMENT', 'Замена слабого грунта', 'м3', 'Земляные работы', 20),
    ('POH', 'DITCH_WORK', 'Устройство водоотводной канавы', 'м2', 'Водоотвод', 30),
    ('VPD', 'SAND_FILL', 'Отсыпка песком', 'м3', 'Основание', 10)
) as v(constructive_code, code, name, unit, report_group, sort_order)
join constructives c on c.code = v.constructive_code
on conflict (code) do nothing;

-- 8. Алиасы видов работ
insert into work_type_aliases (work_type_id, alias_text, match_mode, priority, is_active)
select wt.id, v.alias_text, 'contains', v.priority, true
from (
  values
    ('CUT_SOIL', 'разработка грунта', 10),
    ('CUT_SOIL', 'выемка', 20),
    ('SOIL_REPLACEMENT', 'замена слабого грунта', 10),
    ('DITCH_WORK', 'водоотводная канава', 10),
    ('DITCH_WORK', 'канава', 20),
    ('SAND_FILL', 'отсыпка песком', 10)
) as v(work_code, alias_text, priority)
join work_types wt on wt.code = v.work_code;

-- 9. Техника
insert into equipment (code, equipment_type, fleet_number, model, owner_name, is_active)
values
  ('DUMP-01', 'Самосвал', '451', 'Shacman X3000', 'ООО Генподряд', true),
  ('EXC-01', 'Экскаватор', '233', 'CAT 320', 'ООО Генподряд', true),
  ('BULL-01', 'Бульдозер', '117', 'Komatsu D65', 'ООО Генподряд', true),
  ('DUMP-02', 'Самосвал', '452', 'Shacman X3000', 'ООО Генподряд', true)
on conflict (equipment_type, fleet_number) do nothing;

-- 10. Задачи GSD
insert into gsd_tasks (
  code, title, description, entity_type, status, priority, owner_name, next_action, due_date, blocker_reason
)
values
  ('GSD-001', 'Проверить нераспознанные строки Excel', 'Есть строки с неопределённой дорогой/видом работ', 'excel_import', 'backlog', 'high', 'Инженер ПТО', 'Сверить с исходным файлом', date '2026-03-17', null),
  ('GSD-002', 'Уточнить границу участка 2', 'В Excel граница указана неоднозначно', 'section_boundary', 'in_progress', 'normal', 'Геодезист', 'Запросить подтверждение у стройконтроля', date '2026-03-18', null),
  ('GSD-003', 'Проверить объём по канаве', 'Подозрительно большой объём по водоотводу', 'work_fact', 'backlog', 'high', 'ПТО', 'Сверить с журналом работ', date '2026-03-19', 'Нет фотофиксации'),
  ('GSD-004', 'Закрыть задачу по подъездной дороге', 'Сопоставление выполнено корректно', 'road_mapping', 'done', 'low', 'Система', 'Не требуется', date '2026-03-15', null)
on conflict (code) do nothing;

-- 11. События задач
insert into gsd_task_events (task_id, event_type, old_status, new_status, comment, actor_name)
select t.id, v.event_type, v.old_status, v.new_status, v.comment, v.actor_name
from (
  values
    ('GSD-001', 'created', null, 'backlog', 'Задача создана после импорта Excel', 'agent'),
    ('GSD-002', 'status_change', 'backlog', 'in_progress', 'Передано геодезисту', 'agent'),
    ('GSD-004', 'status_change', 'in_progress', 'done', 'Сопоставление подтверждено', 'operator')
) as v(task_code, event_type, old_status, new_status, comment, actor_name)
join gsd_tasks t on t.code = v.task_code;

-- 12. Чаты
insert into max_chats (max_chat_id, section_id, name, chat_kind, is_active)
select v.max_chat_id, s.id, v.name, v.chat_kind, true
from (
  values
    ('chat-uch1', 'UCH_1', 'Участок 1 — сменный отчёт', 'group'),
    ('chat-uch2', 'UCH_2', 'Участок 2 — сменный отчёт', 'group'),
    ('chat-pto', 'UCH_1', 'ПТО и стройконтроль', 'group')
) as v(max_chat_id, section_code, name, chat_kind)
join construction_sections s on s.code = v.section_code
on conflict (max_chat_id) do nothing;

-- 13. Сообщения
insert into max_messages (
  max_message_id, chat_id, sender_id, sender_name, sent_at, report_date, shift, text_raw, reply_to_message_id, parsed_status
)
select v.max_message_id, c.id, v.sender_id, v.sender_name, v.sent_at, v.report_date, v.shift, v.text_raw, null, v.parsed_status
from (
  values
    ('msg-001', 'chat-uch1', 'u1', 'Мастер участка 1', timestamptz '2026-03-14 18:10:00+00', date '2026-03-14', 'day', 'Разработка грунта ПК2878+00-ПК2885+00, 540 м3', 'parsed'),
    ('msg-002', 'chat-uch1', 'u2', 'Прораб', timestamptz '2026-03-14 18:20:00+00', date '2026-03-14', 'day', 'Устройство водоотводной канавы ПК2890+00-ПК2894+00, 1200 м2', 'parsed'),
    ('msg-003', 'chat-uch2', 'u3', 'Мастер участка 2', timestamptz '2026-03-14 18:25:00+00', date '2026-03-14', 'day', 'Замена слабого грунта ПК2952+00-ПК2951+00, 1550 м3', 'review')
) as v(max_message_id, max_chat_id, sender_id, sender_name, sent_at, report_date, shift, text_raw, parsed_status)
join max_chats c on c.max_chat_id = v.max_chat_id
on conflict (max_message_id) do nothing;

-- 14. Вложения
insert into max_attachments (message_id, attachment_type, file_name, file_url, payload_json)
select m.id, v.attachment_type, v.file_name, v.file_url, v.payload_json::jsonb
from (
  values
    ('msg-001', 'photo', 'soil_001.jpg', 'https://example.local/soil_001.jpg', '{"note":"котлован"}'),
    ('msg-002', 'photo', 'ditch_001.jpg', 'https://example.local/ditch_001.jpg', '{"note":"канава"}'),
    ('msg-003', 'excel', 'shift_report.xlsx', 'https://example.local/shift_report.xlsx', '{"sheet":"Уч. 2"}')
) as v(max_message_id, attachment_type, file_name, file_url, payload_json)
join max_messages m on m.max_message_id = v.max_message_id;

-- 15. Пакет разбора
insert into parse_batches (report_date, started_at, finished_at, status, created_by, note)
values (date '2026-03-14', now(), now(), 'finished', 'agent', 'Демонстрационный пакет разбора')
returning id;

-- 16. Кандидаты разбора
with batch as (
  select id from parse_batches where report_date = date '2026-03-14' order by started_at desc limit 1
), refs as (
  select
    (select id from construction_sections where code = 'UCH_1') as section1_id,
    (select id from construction_sections where code = 'UCH_2') as section2_id,
    (select id from roads where code = 'ROAD_MAIN_TRACK') as road_main_id,
    (select id from roads where code = 'ROAD_TEMP_7') as road_temp_id,
    (select id from constructives where code = 'POH') as poh_id,
    (select id from work_types where code = 'CUT_SOIL') as cut_id,
    (select id from work_types where code = 'DITCH_WORK') as ditch_id,
    (select id from work_types where code = 'SOIL_REPLACEMENT') as repl_id,
    (select id from max_messages where max_message_id = 'msg-001') as msg1_id,
    (select id from max_messages where max_message_id = 'msg-002') as msg2_id,
    (select id from max_messages where max_message_id = 'msg-003') as msg3_id
)
insert into parse_candidates (
  batch_id, message_id, section_id, road_id, constructive_id, work_type_id,
  confidence, volume, unit, pk_raw_text, comment, candidate_json, decision_status, gsd_status
)
select batch.id, x.message_id, x.section_id, x.road_id, x.constructive_id, x.work_type_id,
       x.confidence, x.volume, x.unit, x.pk_raw_text, x.comment, x.candidate_json::jsonb, x.decision_status, x.gsd_status
from batch, refs,
(
  values
    ((select msg1_id from refs), (select section1_id from refs), (select road_main_id from refs), (select poh_id from refs), (select cut_id from refs), 0.96, 540.000, 'м3', 'ПК2878+00-ПК2885+00', 'Распознано уверенно', '{"source":"message"}', 'accepted', 'posted'),
    ((select msg2_id from refs), (select section1_id from refs), (select road_temp_id from refs), (select poh_id from refs), (select ditch_id from refs), 0.89, 1200.000, 'м2', 'ПК2890+00-ПК2894+00', 'Требует подтверждения дороги', '{"source":"message"}', 'pending', 'needs_review'),
    ((select msg3_id from refs), (select section2_id from refs), (select road_main_id from refs), (select poh_id from refs), (select repl_id from refs), 0.74, 1550.000, 'м3', 'ПК2952+00-ПК2951+00', 'Подозрительный обратный интервал', '{"source":"message"}', 'pending', 'needs_review')
) as x(message_id, section_id, road_id, constructive_id, work_type_id, confidence, volume, unit, pk_raw_text, comment, candidate_json, decision_status, gsd_status);

-- 17. Решения оператора
insert into operator_decisions (
  candidate_id, decision, operator_name, final_section_id, final_road_id,
  final_constructive_id, final_work_type_id, final_volume, final_unit, final_comment
)
select pc.id, v.decision, v.operator_name, s.id, r.id, c.id, wt.id, v.final_volume, v.final_unit, v.final_comment
from (
  values
    ('Разработка грунта ПК2878+00-ПК2885+00, 540 м3', 'approve', 'Оператор 1', 'UCH_1', 'ROAD_MAIN_TRACK', 'POH', 'CUT_SOIL', 540.000, 'м3', 'Подтверждено без замечаний'),
    ('Устройство водоотводной канавы ПК2890+00-ПК2894+00, 1200 м2', 'correct', 'Оператор 2', 'UCH_1', 'ROAD_TEMP_7', 'POH', 'DITCH_WORK', 1200.000, 'м2', 'Уточнена привязка к временной дороге')
) as v(message_text, decision, operator_name, section_code, road_code, constructive_code, work_code, final_volume, final_unit, final_comment)
join max_messages mm on mm.text_raw = v.message_text
join parse_candidates pc on pc.message_id = mm.id
join construction_sections s on s.code = v.section_code
join roads r on r.code = v.road_code
join constructives c on c.code = v.constructive_code
join work_types wt on wt.code = v.work_code;

-- 18. Факты работ
insert into work_facts (
  report_date, shift, section_id, road_id, constructive_id, work_type_id,
  volume, unit, pk_raw_text, source_message_id, source_kind, approval_status, gsd_status
)
select v.report_date, v.shift, s.id, r.id, c.id, wt.id,
       v.volume, v.unit, v.pk_raw_text, mm.id, v.source_kind, v.approval_status, v.gsd_status
from (
  values
    (date '2026-03-14', 'day', 'UCH_1', 'ROAD_MAIN_TRACK', 'POH', 'CUT_SOIL', 540.000, 'м3', 'ПК2878+00-ПК2885+00', 'msg-001', 'max', 'approved', 'posted'),
    (date '2026-03-14', 'day', 'UCH_1', 'ROAD_TEMP_7', 'POH', 'DITCH_WORK', 1200.000, 'м2', 'ПК2890+00-ПК2894+00', 'msg-002', 'max', 'approved', 'posted'),
    (date '2026-03-14', 'day', 'UCH_2', 'ROAD_MAIN_TRACK', 'POH', 'SOIL_REPLACEMENT', 1550.000, 'м3', 'ПК2952+00-ПК2951+00', 'msg-003', 'max', 'pending', 'needs_review')
) as v(report_date, shift, section_code, road_code, constructive_code, work_code, volume, unit, pk_raw_text, max_message_id, source_kind, approval_status, gsd_status)
join construction_sections s on s.code = v.section_code
join roads r on r.code = v.road_code
join constructives c on c.code = v.constructive_code
join work_types wt on wt.code = v.work_code
join max_messages mm on mm.max_message_id = v.max_message_id;

-- 19. Сегменты фактов работ
insert into work_fact_segments (work_fact_id, pk_start_m, pk_end_m, pk_start_text, pk_end_text, note)
select wf.id, v.pk_start_m, v.pk_end_m, v.pk_start_text, v.pk_end_text, v.note
from (
  values
    ('msg-001', 287800, 288500, 'ПК2878+00', 'ПК2885+00', 'Разработка грунта'),
    ('msg-002', 289000, 289400, 'ПК2890+00', 'ПК2894+00', 'Водоотводная канава'),
    ('msg-003', 295100, 295200, 'ПК2951+00', 'ПК2952+00', 'Интервал требует проверки направления')
) as v(max_message_id, pk_start_m, pk_end_m, pk_start_text, pk_end_text, note)
join max_messages mm on mm.max_message_id = v.max_message_id
join work_facts wf on wf.source_message_id = mm.id;

-- 20. Использование техники
insert into work_fact_equipment (work_fact_id, equipment_id, shift, trips_count, worked_volume, note)
select wf.id, e.id, v.shift, v.trips_count, v.worked_volume, v.note
from (
  values
    ('msg-001', 'Экскаватор', '233', 'day', 8, 540.000, 'Основная выемка'),
    ('msg-001', 'Самосвал', '451', 'day', 18, 320.000, 'Вывоз грунта'),
    ('msg-002', 'Бульдозер', '117', 'day', 4, 1200.000, 'Планировка канавы'),
    ('msg-003', 'Самосвал', '452', 'day', 22, 1550.000, 'Подвоз материала / вывоз слабого грунта')
) as v(max_message_id, equipment_type, fleet_number, shift, trips_count, worked_volume, note)
join max_messages mm on mm.max_message_id = v.max_message_id
join work_facts wf on wf.source_message_id = mm.id
join equipment e on e.equipment_type = v.equipment_type and e.fleet_number = v.fleet_number;

-- 21. История изменений видов работ
insert into work_type_history (work_type_id, changed_by, old_name, new_name, old_unit, new_unit, comment)
select wt.id, v.changed_by, v.old_name, v.new_name, v.old_unit, v.new_unit, v.comment
from (
  values
    ('CUT_SOIL', 'system', 'Выемка грунта', 'Разработка грунта', 'м3', 'м3', 'Унификация названия'),
    ('DITCH_WORK', 'system', 'Устройство канав', 'Устройство водоотводной канавы', 'м2', 'м2', 'Уточнение формулировки')
) as v(work_code, changed_by, old_name, new_name, old_unit, new_unit, comment)
join work_types wt on wt.code = v.work_code;

-- 22. История изменений границ участков
insert into section_boundary_history (
  section_id, changed_by, old_pk_start_m, old_pk_end_m, new_pk_start_m, new_pk_end_m, comment
)
select s.id, v.changed_by, v.old_pk_start_m, v.old_pk_end_m, v.new_pk_start_m, v.new_pk_end_m, v.comment
from (
  values
    ('UCH_2', 'геодезист', 295000, 301900, 295200, 302000, 'Уточнение после выверки пикетажа'),
    ('UCH_3', 'ПТО', 302000, 309800, 302100, 310000, 'Корректировка по исполнительной схеме')
) as v(section_code, changed_by, old_pk_start_m, old_pk_end_m, new_pk_start_m, new_pk_end_m, comment)
join construction_sections s on s.code = v.section_code;

commit;
