# TASK_web_interface_mvp

## Goal
Собрать и подготовить к деплою MVP веб-интерфейс для существующей PostgreSQL БД `works_db_v2`.

## Rules
- БД не пересоздавать.
- Схему БД не менять без крайней необходимости.
- Mismatch между ТЗ и реальной схемой исправлять в приложении самостоятельно, а не стопорить задачу.
- Если понадобится минимальный логичный patch БД — сначала зафиксировать его отдельно.
- При риске потери контекста обновлять этот файл и сообщать Chel.

## Requested stack
- FastAPI
- Jinja2
- HTMX
- SQLAlchemy 2.x
- Bootstrap 5
- Uvicorn behind Nginx
- Docker Compose

## Current status
- Task accepted after compact.
- Live schema of `works_db_v2` inspected.
- Confirmed actual presence of target tables including `work_item_equipment_usage` and `material_movement_equipment_usage`.
- Built MVP project in `/home/aboba/.openclaw/workspace/works-web-mvp`.
- Added FastAPI app, Jinja2 templates, Bootstrap layout, Dockerfile, docker-compose, nginx config, `.env.example`, README.
- Implemented pages: `/`, `/reports/new`, `/reports/drafts`, `/reports/{id}`, `/reports/{id}/review`, `/work-items`, `/movements`, `/equipment`, `/analytics`, `/analytics/pk`, `/sections`, `/objects`, `/project`.
- Implemented create flows for report draft, work item, work segment, material movement, equipment unit, and review approval.
- Verified key routes with FastAPI TestClient: all returned `200 OK`.
- DB schema was not modified during this MVP task.
