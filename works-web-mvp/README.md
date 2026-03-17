# works-web-mvp

MVP веб-интерфейс для существующей БД `works_db_v2`.

## Что внутри
- FastAPI
- Jinja2 templates
- HTMX
- SQLAlchemy 2.x (reflection от существующей схемы)
- Bootstrap 5
- Nginx reverse proxy
- Docker Compose

## Принцип работы
Приложение подключается к уже существующей PostgreSQL БД `works_db_v2` и работает поверх фактической схемы.

БД не пересоздаётся.
Миграции в MVP не применяются.

## Реализованные страницы
- `/` — главная
- `/reports/new` — создание черновика отчёта
- `/reports/drafts` — черновики
- `/reports/{id}` — карточка отчёта
- `/reports/{id}/review` — экран проверки/подтверждения
- `/work-items` — список работ
- `/movements` — список перевозок
- `/equipment` — список техники
- `/analytics` — базовая аналитика
- `/analytics/pk` — аналитика по пикетажу
- `/sections` — участки
- `/objects` — объекты
- `/project` — проектные объёмы

## Что умеет MVP
- создать `daily_reports` черновик
- создать stub-запись в `daily_report_parse_candidates`
- вручную добавить:
  - `daily_work_items`
  - `daily_work_item_segments`
  - `material_movements`
  - `report_equipment_units`
- подтвердить отчёт оператором через review-экран
- смотреть простую аналитику по существующим данным

## Важные замечания
- Авторазбор текста пока MVP-заглушка, а не полноценный NLP-parser.
- Select-поля пока обычные HTML select, без JS-поиска по справочнику.
- Привязка техники к работам/перевозкам через `work_item_equipment_usage` и `material_movement_equipment_usage` в этом MVP пока только учтена на уровне схемы БД, но отдельный UI для этих связей ещё не сделан.
- Интерфейс сознательно простой и рабочий, без навороченного фронта.

## Локальный запуск без Docker
```bash
cd works-web-mvp
cp .env.example .env
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Запуск в Docker Compose
1. Подготовить env:
```bash
cd works-web-mvp
cp .env.example .env
```

2. Если приложение должно ходить к БД на хосте, оставить:
```env
DB_HOST=host.docker.internal
DB_PORT=5433
```

3. Поднять контейнеры:
```bash
docker compose up -d --build
```

4. Проверить:
```bash
docker compose ps
curl http://127.0.0.1:8082/health
```

## Порты
- приложение внутри compose: `8000`
- nginx снаружи: `${NGINX_PORT}`, по умолчанию `8082`

## Структура
```text
works-web-mvp/
  app/
    main.py
    static/
    templates/
  Dockerfile
  docker-compose.yml
  nginx.conf
  requirements.txt
  .env.example
  README.md
```

## Проверка, которую я уже прогнал
Через TestClient успешно открывались:
- `/`
- `/reports/new`
- `/reports/drafts`
- `/work-items`
- `/movements`
- `/equipment`
- `/analytics`
- `/analytics/pk`
- `/sections`
- `/objects`
- `/project`

Все эти маршруты вернули `200 OK`.
