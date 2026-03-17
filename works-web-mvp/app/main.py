import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
import re

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment
from sqlalchemy import MetaData, Table, and_, case, create_engine, func, insert, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.templating import Jinja2Templates

BASE_DIR = os.path.dirname(__file__)
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")


def env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing env var: {name}")
    return value


DATABASE_URL = (
    f"postgresql+psycopg2://{env('DB_USER', 'works_user')}:{env('DB_PASSWORD', '')}"
    f"@{env('DB_HOST', '127.0.0.1')}:{env('DB_PORT', '5433')}/{env('DB_NAME', 'works_db_v2')}"
)

engine: Engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
metadata = MetaData()
metadata.reflect(bind=engine, schema="public")

construction_sections = metadata.tables["public.construction_sections"]
construction_section_versions = metadata.tables["public.construction_section_versions"]
constructives = metadata.tables["public.constructives"]
object_types = metadata.tables["public.object_types"]
objects = metadata.tables["public.objects"]
object_segments = metadata.tables["public.object_segments"]
work_types = metadata.tables["public.work_types"]
daily_reports = metadata.tables["public.daily_reports"]
daily_report_parse_candidates = metadata.tables["public.daily_report_parse_candidates"]
daily_work_items = metadata.tables["public.daily_work_items"]
daily_work_item_segments = metadata.tables["public.daily_work_item_segments"]
materials = metadata.tables["public.materials"]
material_movements = metadata.tables["public.material_movements"]
report_equipment_units = metadata.tables["public.report_equipment_units"]
project_work_items = metadata.tables["public.project_work_items"]
project_work_item_segments = metadata.tables["public.project_work_item_segments"]
stockpiles = metadata.tables["public.stockpiles"]
stockpile_balance_snapshots = metadata.tables["public.stockpile_balance_snapshots"]
work_item_equipment_usage = metadata.tables["public.work_item_equipment_usage"]
material_movement_equipment_usage = metadata.tables["public.material_movement_equipment_usage"]

app = FastAPI(title="Works DB MVP")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def to_decimal(value: str | None):
    if value in (None, ""):
        return None
    return Decimal(str(value).replace(",", "."))


def to_uuid_or_none(value: str | None):
    return value or None


def normalize_shift(raw_text: str | None, fallback: str) -> str:
    text = (raw_text or '').lower()
    if 'ноч' in text:
        return 'night'
    if 'день' in text or '/д/' in text:
        return 'day'
    return fallback


def extract_report_date(raw_text: str | None, fallback: str) -> str:
    text = raw_text or ''
    m = re.search(r'(\d{2})\.(\d{2})\.(\d{2,4})', text)
    if not m:
        return fallback
    dd, mm, yy = m.groups()
    year = int(yy)
    if year < 100:
        year += 2000
    return f"{year:04d}-{int(mm):02d}-{int(dd):02d}"


def extract_section_number(raw_text: str | None) -> str | None:
    text = raw_text or ''
    m = re.search(r'участок\s*№?\s*(\d+)', text, flags=re.I)
    return m.group(1) if m else None


def match_section_id(db: Session, section_number: str | None, fallback_section_id: str):
    if not section_number:
        return fallback_section_id
    rows = db.execute(select(construction_sections.c.id, construction_sections.c.name, construction_sections.c.code)).all()
    for sid, name, code in rows:
        blob = f"{name or ''} {code or ''}".lower()
        if section_number in blob:
            return sid
    return fallback_section_id


def classify_line(line: str) -> str:
    low = line.lower()
    if any(word in low for word in ['самосвал', 'экскават', 'бульдоз', 'каток', 'грейдер', 'погрузчик', 'манипулятор', 'трал']):
        return 'equipment'
    if any(word in low for word in ['перевоз', 'рейс', 'доставка', 'вывоз', 'отгруз', 'погрузка']) and any(word in low for word in ['грунт', 'пес', 'щеб', 'материал', 'торф']):
        return 'movement'
    if any(word in low for word in ['персонал', 'водитель', 'машинист', 'итр', 'учетчик']):
        return 'personnel'
    return 'work'


def heuristic_extract_entities(raw_text: str | None) -> dict:
    text = raw_text or ''
    lines = [ln.strip(' -	') for ln in text.splitlines() if ln.strip()]
    work_lines = []
    movement_lines = []
    equipment_lines = []
    personnel_lines = []
    report_date = None
    for line in lines:
        if not report_date:
            m = re.search(r'(\d{2}\.\d{2}\.\d{2,4})', line)
            if m:
                report_date = m.group(1)
        classified = None
        if re.match(r'^\d+[.)]', line):
            classified = classify_line(line)
        elif any(x in line.lower() for x in ['участок', 'ст.', 'путь', 'а/д']):
            continue
        else:
            classified = classify_line(line)
        if classified == 'movement':
            movement_lines.append(line)
        elif classified == 'equipment':
            equipment_lines.append(line)
        elif classified == 'personnel':
            personnel_lines.append(line)
        elif classified == 'work' and re.match(r'^\d+[.)]', line):
            work_lines.append(line)
    return {
        'header': {
            'report_date_raw': report_date,
            'section_number': extract_section_number(text),
            'shift_guess': 'night' if 'ноч' in text.lower() else ('day' if 'день' in text.lower() else None),
        },
        'work_lines': work_lines[:40],
        'movement_lines': movement_lines[:40],
        'equipment_mentions': equipment_lines[:40],
        'personnel_mentions': personnel_lines[:40],
    }


def create_entities_from_raw_text(db: Session, report_id, raw_text: str | None, report_row):
    entities = heuristic_extract_entities(raw_text)
    work_type_rows = db.execute(select(work_types.c.id, work_types.c.name).where(work_types.c.is_active.is_(True))).all()
    work_name_map = [(str(name).lower(), wid) for wid, name in work_type_rows if name]
    material_rows = db.execute(select(materials.c.id, materials.c.name)).all()
    material_map = [(str(name).lower(), mid) for mid, name in material_rows if name]
    created = {'work_items': 0, 'movements': 0, 'equipment': 0}
    for line in entities['work_lines']:
        norm = re.sub(r'^\d+[.)]\s*', '', line).strip()
        matched_work_type = None
        for name, wid in work_name_map:
            if name and (name in norm.lower() or norm.lower() in name):
                matched_work_type = wid
                break
        db.execute(insert(daily_work_items).values(
            id=uuid4(),
            daily_report_id=report_id,
            report_date=report_row['report_date'],
            shift=report_row['shift'],
            section_id=report_row['section_id'],
            work_type_id=matched_work_type,
            work_name_raw=norm[:1000],
            labor_source_type='unknown',
            comment='Автосоздано из текста отчета (MVP heuristic)',
        ))
        created['work_items'] += 1
    for line in entities['movement_lines']:
        norm = re.sub(r'^\d+[.)]\s*', '', line).strip()
        matched_material = None
        for name, mid in material_map:
            if name and name in norm.lower():
                matched_material = mid
                break
        if matched_material:
            db.execute(insert(material_movements).values(
                id=uuid4(),
                daily_report_id=report_id,
                report_date=report_row['report_date'],
                shift=report_row['shift'],
                section_id=report_row['section_id'],
                material_id=matched_material,
                movement_type='other',
                labor_source_type='unknown',
                comment='Автосоздано из текста отчета (MVP heuristic): ' + norm[:500],
            ))
            created['movements'] += 1
    for line in entities['equipment_mentions']:
        norm = re.sub(r'^\d+[.)]\s*', '', line).strip()
        equipment_type = 'unknown'
        low = norm.lower()
        for key in ['самосвал', 'экскаватор', 'бульдозер', 'каток', 'грейдер', 'погрузчик', 'манипулятор', 'трал']:
            if key in low:
                equipment_type = key
                break
        qty_match = re.search(r'(\d+)\s*(ед|шт|чел)?', low)
        qty = int(qty_match.group(1)) if qty_match else 1
        qty = max(1, min(qty, 10))
        for idx in range(qty):
            db.execute(insert(report_equipment_units).values(
                id=uuid4(),
                daily_report_id=report_id,
                equipment_type=equipment_type,
                brand_model=norm[:200],
                ownership_type='unknown',
                status='working',
                comment='Автосоздано из текста отчета (MVP heuristic)',
            ))
            created['equipment'] += 1
    return entities, created


def all_lookup_rows(db: Session):
    sections_q = select(construction_sections).where(construction_sections.c.is_active.is_(True)).order_by(construction_sections.c.name)
    objs_q = select(objects).where(objects.c.is_active.is_(True)).order_by(objects.c.name)
    constr_q = select(constructives).where(constructives.c.is_active.is_(True)).order_by(constructives.c.sort_order, constructives.c.name)
    work_types_q = select(work_types).where(work_types.c.is_active.is_(True)).order_by(work_types.c.name)
    materials_q = select(materials).order_by(materials.c.name)
    report_rows = db.execute(sections_q).mappings().all()
    return {
        "sections": report_rows,
        "objects": db.execute(objs_q).mappings().all(),
        "constructives": db.execute(constr_q).mappings().all(),
        "work_types": db.execute(work_types_q).mappings().all(),
        "materials": db.execute(materials_q).mappings().all(),
    }


def parse_candidates_for_report(db: Session, report_id):
    rows = db.execute(
        select(daily_report_parse_candidates)
        .where(daily_report_parse_candidates.c.daily_report_id == report_id)
        .order_by(daily_report_parse_candidates.c.created_at.desc())
    ).mappings().all()
    return rows


def report_detail(db: Session, report_id):
    section_name = construction_sections.c.name.label("section_name")
    stmt = (
        select(daily_reports, section_name)
        .select_from(daily_reports.outerjoin(construction_sections, construction_sections.c.id == daily_reports.c.section_id))
        .where(daily_reports.c.id == report_id)
    )
    return db.execute(stmt).mappings().first()


def work_items_for_report(db: Session, report_id):
    stmt = (
        select(
            daily_work_items,
            objects.c.name.label("object_name"),
            constructives.c.name.label("constructive_name"),
            work_types.c.name.label("work_type_name"),
        )
        .select_from(
            daily_work_items.outerjoin(objects, objects.c.id == daily_work_items.c.object_id)
            .outerjoin(constructives, constructives.c.id == daily_work_items.c.constructive_id)
            .outerjoin(work_types, work_types.c.id == daily_work_items.c.work_type_id)
        )
        .where(daily_work_items.c.daily_report_id == report_id)
        .order_by(daily_work_items.c.created_at.desc())
    )
    rows = db.execute(stmt).mappings().all()
    if not rows:
        return []
    item_ids = [r["id"] for r in rows]
    seg_stmt = (
        select(daily_work_item_segments)
        .where(daily_work_item_segments.c.daily_work_item_id.in_(item_ids))
        .order_by(daily_work_item_segments.c.created_at.asc())
    )
    segs = db.execute(seg_stmt).mappings().all()
    grouped = {}
    for seg in segs:
        grouped.setdefault(seg["daily_work_item_id"], []).append(seg)
    enriched = []
    for row in rows:
        item = dict(row)
        item["segments"] = grouped.get(row["id"], [])
        enriched.append(item)
    return enriched


def movements_for_report(db: Session, report_id):
    stmt = (
        select(
            material_movements,
            materials.c.name.label("material_name"),
            objects.alias("from_obj").c.name.label("from_object_name"),
            objects.alias("to_obj").c.name.label("to_object_name"),
        )
        .select_from(material_movements)
        .join(materials, materials.c.id == material_movements.c.material_id, isouter=True)
    )
    # object aliases handled separately below to keep reflection simple
    from_obj = objects.alias("from_obj")
    to_obj = objects.alias("to_obj")
    stmt = (
        select(
            material_movements,
            materials.c.name.label("material_name"),
            from_obj.c.name.label("from_object_name"),
            to_obj.c.name.label("to_object_name"),
        )
        .select_from(
            material_movements.outerjoin(materials, materials.c.id == material_movements.c.material_id)
            .outerjoin(from_obj, from_obj.c.id == material_movements.c.from_object_id)
            .outerjoin(to_obj, to_obj.c.id == material_movements.c.to_object_id)
        )
        .where(material_movements.c.daily_report_id == report_id)
        .order_by(material_movements.c.created_at.desc())
    )
    return db.execute(stmt).mappings().all()


def equipment_for_report(db: Session, report_id):
    stmt = (
        select(report_equipment_units)
        .where(report_equipment_units.c.daily_report_id == report_id)
        .order_by(report_equipment_units.c.created_at.desc())
    )
    rows = db.execute(stmt).mappings().all()
    if not rows:
        return []
    equipment_ids = [r["id"] for r in rows]
    work_usage_rows = db.execute(
        select(
            work_item_equipment_usage,
            daily_work_items.c.work_name_raw,
            work_types.c.name.label("work_type_name"),
        )
        .select_from(
            work_item_equipment_usage.join(daily_work_items, daily_work_items.c.id == work_item_equipment_usage.c.daily_work_item_id)
            .outerjoin(work_types, work_types.c.id == daily_work_items.c.work_type_id)
        )
        .where(work_item_equipment_usage.c.report_equipment_unit_id.in_(equipment_ids))
        .order_by(work_item_equipment_usage.c.created_at.asc())
    ).mappings().all()
    movement_usage_rows = db.execute(
        select(
            material_movement_equipment_usage,
            materials.c.name.label("material_name"),
            material_movements.c.movement_type,
        )
        .select_from(
            material_movement_equipment_usage.join(material_movements, material_movements.c.id == material_movement_equipment_usage.c.material_movement_id)
            .outerjoin(materials, materials.c.id == material_movements.c.material_id)
        )
        .where(material_movement_equipment_usage.c.report_equipment_unit_id.in_(equipment_ids))
        .order_by(material_movement_equipment_usage.c.created_at.asc())
    ).mappings().all()
    work_map = {}
    for row in work_usage_rows:
        work_map.setdefault(row["report_equipment_unit_id"], []).append(dict(row))
    mov_map = {}
    for row in movement_usage_rows:
        mov_map.setdefault(row["report_equipment_unit_id"], []).append(dict(row))
    result = []
    for row in rows:
        item = dict(row)
        item["work_usage"] = work_map.get(row["id"], [])
        item["movement_usage"] = mov_map.get(row["id"], [])
        result.append(item)
    return result


def enrich_work_items_with_usage(db: Session, items):
    if not items:
        return items
    item_ids = [r["id"] for r in items]
    usage_rows = db.execute(
        select(
            work_item_equipment_usage,
            report_equipment_units.c.equipment_type,
            report_equipment_units.c.brand_model,
            report_equipment_units.c.unit_number,
            report_equipment_units.c.plate_number,
            report_equipment_units.c.ownership_type,
            report_equipment_units.c.contractor_name,
        )
        .select_from(
            work_item_equipment_usage.join(report_equipment_units, report_equipment_units.c.id == work_item_equipment_usage.c.report_equipment_unit_id)
        )
        .where(work_item_equipment_usage.c.daily_work_item_id.in_(item_ids))
        .order_by(work_item_equipment_usage.c.created_at.asc())
    ).mappings().all()
    usage_map = {}
    for row in usage_rows:
        usage_map.setdefault(row["daily_work_item_id"], []).append(dict(row))
    for item in items:
        item["equipment_usage"] = usage_map.get(item["id"], [])
    return items


def enrich_movements_with_usage(db: Session, rows):
    if not rows:
        return rows
    movement_ids = [r["id"] for r in rows]
    usage_rows = db.execute(
        select(
            material_movement_equipment_usage,
            report_equipment_units.c.equipment_type,
            report_equipment_units.c.brand_model,
            report_equipment_units.c.unit_number,
            report_equipment_units.c.plate_number,
            report_equipment_units.c.ownership_type,
            report_equipment_units.c.contractor_name,
        )
        .select_from(material_movement_equipment_usage.join(report_equipment_units, report_equipment_units.c.id == material_movement_equipment_usage.c.report_equipment_unit_id))
        .where(material_movement_equipment_usage.c.material_movement_id.in_(movement_ids))
        .order_by(material_movement_equipment_usage.c.created_at.asc())
    ).mappings().all()
    usage_map = {}
    for row in usage_rows:
        usage_map.setdefault(row["material_movement_id"], []).append(dict(row))
    for row in rows:
        row["equipment_usage"] = usage_map.get(row["id"], [])
    return rows


def create_parse_candidate(db: Session, report_id, raw_text: str | None):
    extracted = heuristic_extract_entities(raw_text)
    payload = {
        "raw_text_present": bool(raw_text and raw_text.strip()),
        "note": "MVP heuristic parse. Требуется ручная проверка оператором.",
        "preview": (raw_text or "")[:500],
        **extracted,
    }
    db.execute(
        insert(daily_report_parse_candidates).values(
            id=uuid4(),
            daily_report_id=report_id,
            candidate_type="heuristic_parse",
            payload_json=payload,
            confidence=Decimal("0.55") if (extracted['work_lines'] or extracted['movement_lines'] or extracted['equipment_mentions']) else Decimal("0.15"),
            needs_manual_review=True,
            comment="Создано MVP-эвристическим разбором",
        )
    )


def base_context(request: Request, db: Session):
    today = date.today()
    drafts_count = db.execute(
        select(func.count()).select_from(daily_reports).where(
            or_(daily_reports.c.operator_status.is_(None), daily_reports.c.operator_status == "pending")
        )
    ).scalar_one()
    confirmed_count = db.execute(
        select(func.count()).select_from(daily_work_items).where(daily_work_items.c.report_date == today)
    ).scalar_one()
    movements_today = db.execute(
        select(func.count()).select_from(material_movements).where(material_movements.c.report_date == today)
    ).scalar_one()
    equipment_today = db.execute(
        select(func.count())
        .select_from(report_equipment_units.join(daily_reports, daily_reports.c.id == report_equipment_units.c.daily_report_id))
        .where(daily_reports.c.report_date == today)
    ).scalar_one()
    return {
        "request": request,
        "today": today,
        "nav": [
            ("/", "Главная"),
            ("/reports/new", "Новый отчет"),
            ("/reports/drafts", "Черновики"),
            ("/work-items", "Работы"),
            ("/movements", "Перевозки"),
            ("/equipment", "Техника"),
            ("/analytics", "Аналитика"),
            ("/analytics/pk", "По пикетажу"),
            ("/sections", "Участки"),
            ("/objects", "Объекты"),
            ("/project", "Проект"),
        ],
        "header_stats": {
            "drafts": drafts_count,
            "work_items_today": confirmed_count,
            "movements_today": movements_today,
            "equipment_today": equipment_today,
        },
    }


@app.get("/health")
def health():
    with SessionLocal() as db:
        db.execute(select(func.now()))
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    with SessionLocal() as db:
        ctx = base_context(request, db)
        drafts = db.execute(
            select(daily_reports, construction_sections.c.name.label("section_name"))
            .select_from(daily_reports.outerjoin(construction_sections, construction_sections.c.id == daily_reports.c.section_id))
            .where(or_(daily_reports.c.operator_status.is_(None), daily_reports.c.operator_status == "pending"))
            .order_by(daily_reports.c.report_date.desc(), daily_reports.c.created_at.desc())
            .limit(10)
        ).mappings().all()
        confirmed = db.execute(
            select(daily_reports, construction_sections.c.name.label("section_name"))
            .select_from(daily_reports.outerjoin(construction_sections, construction_sections.c.id == daily_reports.c.section_id))
            .where(daily_reports.c.operator_status == "approved")
            .order_by(daily_reports.c.report_date.desc(), daily_reports.c.created_at.desc())
            .limit(10)
        ).mappings().all()
        today = date.today()
        ctx.update(
            drafts=drafts,
            confirmed=confirmed,
            today_summary={
                "reports": db.execute(select(func.count()).select_from(daily_reports).where(daily_reports.c.report_date == today)).scalar_one(),
                "work_items": db.execute(select(func.count()).select_from(daily_work_items).where(daily_work_items.c.report_date == today)).scalar_one(),
                "movements": db.execute(select(func.count()).select_from(material_movements).where(material_movements.c.report_date == today)).scalar_one(),
                "equipment": db.execute(
                    select(func.count()).select_from(report_equipment_units.join(daily_reports, daily_reports.c.id == report_equipment_units.c.daily_report_id))
                    .where(daily_reports.c.report_date == today)
                ).scalar_one(),
            },
        )
        return templates.TemplateResponse("home.html", ctx)


@app.get("/reports/new", response_class=HTMLResponse)
def reports_new(request: Request):
    with SessionLocal() as db:
        ctx = base_context(request, db)
        ctx.update(all_lookup_rows(db))
        return templates.TemplateResponse("reports_new.html", ctx)


@app.post("/reports/new")
def reports_new_submit(
    report_date: str = Form(...),
    shift: str = Form(...),
    section_id: str = Form(...),
    source_type: str = Form(...),
    source_reference: str = Form(""),
    raw_text: str = Form(""),
):
    report_id = uuid4()
    with SessionLocal() as db:
        parsed_date = extract_report_date(raw_text, report_date)
        parsed_shift = normalize_shift(raw_text, shift)
        parsed_section_id = match_section_id(db, extract_section_number(raw_text), section_id)
        db.execute(
            insert(daily_reports).values(
                id=report_id,
                report_date=parsed_date,
                shift=parsed_shift,
                section_id=parsed_section_id,
                source_type=source_type,
                source_reference=source_reference or None,
                raw_text=raw_text or None,
                parse_status="needs_review" if raw_text else "new",
                operator_status="pending",
            )
        )
        report_row = {
            'report_date': parsed_date,
            'shift': parsed_shift,
            'section_id': parsed_section_id,
        }
        if raw_text.strip():
            create_parse_candidate(db, report_id, raw_text)
            create_entities_from_raw_text(db, report_id, raw_text, report_row)
        db.commit()
    return RedirectResponse(url=f"/reports/{report_id}", status_code=303)


@app.get("/reports/drafts", response_class=HTMLResponse)
def reports_drafts(request: Request):
    with SessionLocal() as db:
        ctx = base_context(request, db)
        rows = db.execute(
            select(daily_reports, construction_sections.c.name.label("section_name"))
            .select_from(daily_reports.outerjoin(construction_sections, construction_sections.c.id == daily_reports.c.section_id))
            .where(or_(daily_reports.c.operator_status.is_(None), daily_reports.c.operator_status == "pending"))
            .order_by(daily_reports.c.report_date.desc(), daily_reports.c.created_at.desc())
        ).mappings().all()
        ctx["drafts"] = rows
        return templates.TemplateResponse("reports_drafts.html", ctx)


@app.get("/reports/{report_id}", response_class=HTMLResponse)
def report_card(request: Request, report_id: str):
    with SessionLocal() as db:
        report = report_detail(db, report_id)
        if not report:
            raise HTTPException(404, "Report not found")
        ctx = base_context(request, db)
        ctx.update(all_lookup_rows(db))
        work_items = enrich_work_items_with_usage(db, work_items_for_report(db, report_id))
        movements = enrich_movements_with_usage(db, movements_for_report(db, report_id))
        ctx.update(
            report=report,
            candidates=parse_candidates_for_report(db, report_id),
            work_items=work_items,
            movements=movements,
            equipment=equipment_for_report(db, report_id),
        )
        return templates.TemplateResponse("report_card.html", ctx)


@app.post("/reports/{report_id}/review/approve")
def approve_report(report_id: str, approved_by: str = Form("operator")):
    with SessionLocal() as db:
        db.execute(
            daily_reports.update()
            .where(daily_reports.c.id == report_id)
            .values(operator_status="approved", parse_status="approved")
        )
        db.execute(
            daily_work_items.update()
            .where(and_(daily_work_items.c.daily_report_id == report_id, daily_work_items.c.approved_at.is_(None)))
            .values(approved_by=approved_by, approved_at=now_utc())
        )
        db.execute(
            material_movements.update()
            .where(and_(material_movements.c.daily_report_id == report_id, material_movements.c.approved_at.is_(None)))
            .values(approved_by=approved_by, approved_at=now_utc())
        )
        db.commit()
    return RedirectResponse(url=f"/reports/{report_id}/review", status_code=303)


@app.get("/reports/{report_id}/review", response_class=HTMLResponse)
def review_report(request: Request, report_id: str):
    with SessionLocal() as db:
        report = report_detail(db, report_id)
        if not report:
            raise HTTPException(404, "Report not found")
        ctx = base_context(request, db)
        work_items = enrich_work_items_with_usage(db, work_items_for_report(db, report_id))
        movements = enrich_movements_with_usage(db, movements_for_report(db, report_id))
        ctx.update(
            report=report,
            candidates=parse_candidates_for_report(db, report_id),
            work_items=work_items,
            movements=movements,
            equipment=equipment_for_report(db, report_id),
        )
        return templates.TemplateResponse("report_review.html", ctx)


@app.post("/reports/{report_id}/work-items")
def add_work_item(
    report_id: str,
    object_id: str = Form(""),
    constructive_id: str = Form(""),
    work_type_id: str = Form(""),
    work_name_raw: str = Form(""),
    unit: str = Form(""),
    volume: str = Form(""),
    labor_source_type: str = Form("unknown"),
    contractor_name: str = Form(""),
    comment: str = Form(""),
):
    with SessionLocal() as db:
        report = report_detail(db, report_id)
        if not report:
            raise HTTPException(404, "Report not found")
        db.execute(
            insert(daily_work_items).values(
                id=uuid4(),
                daily_report_id=report_id,
                report_date=report["report_date"],
                shift=report["shift"],
                section_id=report["section_id"],
                object_id=object_id or None,
                constructive_id=constructive_id or None,
                work_type_id=work_type_id or None,
                work_name_raw=work_name_raw or None,
                unit=unit or None,
                volume=to_decimal(volume),
                labor_source_type=labor_source_type or "unknown",
                contractor_name=contractor_name or None,
                comment=comment or None,
            )
        )
        db.execute(daily_reports.update().where(daily_reports.c.id == report_id).values(operator_status="pending"))
        db.commit()
    return RedirectResponse(url=f"/reports/{report_id}", status_code=303)


@app.post("/work-items/{item_id}/segments")
def add_work_segment(
    item_id: str,
    pk_start: str = Form(...),
    pk_end: str = Form(...),
    volume_segment: str = Form(""),
    pk_raw_text: str = Form(""),
    comment: str = Form(""),
):
    with SessionLocal() as db:
        db.execute(
            insert(daily_work_item_segments).values(
                id=uuid4(),
                daily_work_item_id=item_id,
                pk_start=to_decimal(pk_start),
                pk_end=to_decimal(pk_end),
                volume_segment=to_decimal(volume_segment),
                pk_raw_text=pk_raw_text or None,
                comment=comment or None,
            )
        )
        report_id = db.execute(select(daily_work_items.c.daily_report_id).where(daily_work_items.c.id == item_id)).scalar_one()
        db.execute(daily_reports.update().where(daily_reports.c.id == report_id).values(operator_status="pending"))
        db.commit()
    return RedirectResponse(url=f"/reports/{report_id}", status_code=303)


@app.post("/reports/{report_id}/movements")
def add_movement(
    report_id: str,
    material_id: str = Form(...),
    from_object_id: str = Form(""),
    to_object_id: str = Form(""),
    volume: str = Form(""),
    unit: str = Form(""),
    trip_count: str = Form(""),
    movement_type: str = Form("other"),
    labor_source_type: str = Form("unknown"),
    contractor_name: str = Form(""),
    comment: str = Form(""),
):
    with SessionLocal() as db:
        report = report_detail(db, report_id)
        if not report:
            raise HTTPException(404, "Report not found")
        db.execute(
            insert(material_movements).values(
                id=uuid4(),
                daily_report_id=report_id,
                report_date=report["report_date"],
                shift=report["shift"],
                section_id=report["section_id"],
                material_id=material_id,
                from_object_id=from_object_id or None,
                to_object_id=to_object_id or None,
                volume=to_decimal(volume),
                unit=unit or None,
                trip_count=to_int(trip_count),
                movement_type=movement_type,
                labor_source_type=labor_source_type,
                contractor_name=contractor_name or None,
                comment=comment or None,
            )
        )
        db.execute(daily_reports.update().where(daily_reports.c.id == report_id).values(operator_status="pending"))
        db.commit()
    return RedirectResponse(url=f"/reports/{report_id}", status_code=303)


@app.post("/reports/{report_id}/equipment")
def add_equipment(
    report_id: str,
    equipment_type: str = Form(...),
    brand_model: str = Form(""),
    unit_number: str = Form(""),
    plate_number: str = Form(""),
    operator_name: str = Form(""),
    ownership_type: str = Form("unknown"),
    contractor_name: str = Form(""),
    status: str = Form("unknown"),
    comment: str = Form(""),
):
    with SessionLocal() as db:
        db.execute(
            insert(report_equipment_units).values(
                id=uuid4(),
                daily_report_id=report_id,
                equipment_type=equipment_type,
                brand_model=brand_model or None,
                unit_number=unit_number or None,
                plate_number=plate_number or None,
                operator_name=operator_name or None,
                ownership_type=ownership_type,
                contractor_name=contractor_name or None,
                status=status,
                comment=comment or None,
            )
        )
        db.execute(daily_reports.update().where(daily_reports.c.id == report_id).values(operator_status="pending"))
        db.commit()
    return RedirectResponse(url=f"/reports/{report_id}", status_code=303)


@app.post("/work-items/{item_id}/equipment-usage")
def add_work_item_equipment_usage(
    item_id: str,
    report_equipment_unit_id: str = Form(...),
    trips_count: str = Form(""),
    worked_volume: str = Form(""),
    worked_area: str = Form(""),
    worked_length: str = Form(""),
    comment: str = Form(""),
):
    with SessionLocal() as db:
        report_id = db.execute(select(daily_work_items.c.daily_report_id).where(daily_work_items.c.id == item_id)).scalar_one()
        db.execute(
            insert(work_item_equipment_usage).values(
                id=uuid4(),
                daily_work_item_id=item_id,
                report_equipment_unit_id=report_equipment_unit_id,
                trips_count=to_int(trips_count),
                worked_volume=to_decimal(worked_volume),
                worked_area=to_decimal(worked_area),
                worked_length=to_decimal(worked_length),
                comment=comment or None,
            )
        )
        db.execute(daily_reports.update().where(daily_reports.c.id == report_id).values(operator_status="pending"))
        db.commit()
    return RedirectResponse(url=f"/reports/{report_id}", status_code=303)


@app.post("/movements/{movement_id}/equipment-usage")
def add_movement_equipment_usage(
    movement_id: str,
    report_equipment_unit_id: str = Form(...),
    trips_count: str = Form(""),
    worked_volume: str = Form(""),
    comment: str = Form(""),
):
    with SessionLocal() as db:
        report_id = db.execute(select(material_movements.c.daily_report_id).where(material_movements.c.id == movement_id)).scalar_one()
        db.execute(
            insert(material_movement_equipment_usage).values(
                id=uuid4(),
                material_movement_id=movement_id,
                report_equipment_unit_id=report_equipment_unit_id,
                trips_count=to_int(trips_count),
                worked_volume=to_decimal(worked_volume),
                comment=comment or None,
            )
        )
        db.execute(daily_reports.update().where(daily_reports.c.id == report_id).values(operator_status="pending"))
        db.commit()
    return RedirectResponse(url=f"/reports/{report_id}", status_code=303)


@app.post("/reports/{report_id}/edit-header")
def edit_report_header(
    report_id: str,
    report_date: str = Form(...),
    shift: str = Form(...),
    section_id: str = Form(...),
    source_type: str = Form(...),
    source_reference: str = Form(""),
    raw_text: str = Form(""),
):
    with SessionLocal() as db:
        db.execute(daily_reports.update().where(daily_reports.c.id == report_id).values(
            report_date=report_date,
            shift=shift,
            section_id=section_id,
            source_type=source_type,
            source_reference=source_reference or None,
            raw_text=raw_text or None,
            operator_status='pending',
        ))
        db.commit()
    return RedirectResponse(url=f"/reports/{report_id}", status_code=303)


@app.post("/work-items/{item_id}/edit")
def edit_work_item(
    item_id: str,
    object_id: str = Form(""),
    constructive_id: str = Form(""),
    work_type_id: str = Form(""),
    work_name_raw: str = Form(""),
    unit: str = Form(""),
    volume: str = Form(""),
    labor_source_type: str = Form("unknown"),
    contractor_name: str = Form(""),
    comment: str = Form(""),
):
    with SessionLocal() as db:
        report_id = db.execute(select(daily_work_items.c.daily_report_id).where(daily_work_items.c.id == item_id)).scalar_one()
        db.execute(daily_work_items.update().where(daily_work_items.c.id == item_id).values(
            object_id=to_uuid_or_none(object_id),
            constructive_id=to_uuid_or_none(constructive_id),
            work_type_id=to_uuid_or_none(work_type_id),
            work_name_raw=work_name_raw or None,
            unit=unit or None,
            volume=to_decimal(volume),
            labor_source_type=labor_source_type,
            contractor_name=contractor_name or None,
            comment=comment or None,
        ))
        db.commit()
    return RedirectResponse(url=f"/reports/{report_id}", status_code=303)


@app.post("/movements/{movement_id}/edit")
def edit_movement(
    movement_id: str,
    material_id: str = Form(...),
    from_object_id: str = Form(""),
    to_object_id: str = Form(""),
    volume: str = Form(""),
    unit: str = Form(""),
    trip_count: str = Form(""),
    movement_type: str = Form("other"),
    labor_source_type: str = Form("unknown"),
    contractor_name: str = Form(""),
    comment: str = Form(""),
):
    with SessionLocal() as db:
        report_id = db.execute(select(material_movements.c.daily_report_id).where(material_movements.c.id == movement_id)).scalar_one()
        db.execute(material_movements.update().where(material_movements.c.id == movement_id).values(
            material_id=material_id,
            from_object_id=to_uuid_or_none(from_object_id),
            to_object_id=to_uuid_or_none(to_object_id),
            volume=to_decimal(volume),
            unit=unit or None,
            trip_count=to_int(trip_count),
            movement_type=movement_type,
            labor_source_type=labor_source_type,
            contractor_name=contractor_name or None,
            comment=comment or None,
        ))
        db.commit()
    return RedirectResponse(url=f"/reports/{report_id}", status_code=303)


@app.post("/equipment/{equipment_id}/edit")
def edit_equipment(
    equipment_id: str,
    equipment_type: str = Form(...),
    brand_model: str = Form(""),
    unit_number: str = Form(""),
    plate_number: str = Form(""),
    operator_name: str = Form(""),
    ownership_type: str = Form("unknown"),
    contractor_name: str = Form(""),
    status: str = Form("unknown"),
    comment: str = Form(""),
):
    with SessionLocal() as db:
        report_id = db.execute(select(report_equipment_units.c.daily_report_id).where(report_equipment_units.c.id == equipment_id)).scalar_one()
        db.execute(report_equipment_units.update().where(report_equipment_units.c.id == equipment_id).values(
            equipment_type=equipment_type,
            brand_model=brand_model or None,
            unit_number=unit_number or None,
            plate_number=plate_number or None,
            operator_name=operator_name or None,
            ownership_type=ownership_type,
            contractor_name=contractor_name or None,
            status=status,
            comment=comment or None,
        ))
        db.commit()
    return RedirectResponse(url=f"/reports/{report_id}", status_code=303)


@app.get("/work-items", response_class=HTMLResponse)
def work_items_page(request: Request, days: int = 14):
    with SessionLocal() as db:
        ctx = base_context(request, db)
        since = date.today() - timedelta(days=days)
        stmt = (
            select(
                daily_work_items,
                construction_sections.c.name.label("section_name"),
                objects.c.name.label("object_name"),
                work_types.c.name.label("work_type_name"),
            )
            .select_from(
                daily_work_items.outerjoin(construction_sections, construction_sections.c.id == daily_work_items.c.section_id)
                .outerjoin(objects, objects.c.id == daily_work_items.c.object_id)
                .outerjoin(work_types, work_types.c.id == daily_work_items.c.work_type_id)
            )
            .where(daily_work_items.c.report_date >= since)
            .order_by(daily_work_items.c.report_date.desc(), daily_work_items.c.created_at.desc())
            .limit(300)
        )
        ctx.update(rows=db.execute(stmt).mappings().all(), days=days)
        return templates.TemplateResponse("work_items.html", ctx)


@app.get("/movements", response_class=HTMLResponse)
def movements_page(request: Request, days: int = 14):
    with SessionLocal() as db:
        ctx = base_context(request, db)
        since = date.today() - timedelta(days=days)
        from_obj = objects.alias("from_obj")
        to_obj = objects.alias("to_obj")
        stmt = (
            select(
                material_movements,
                construction_sections.c.name.label("section_name"),
                materials.c.name.label("material_name"),
                from_obj.c.name.label("from_object_name"),
                to_obj.c.name.label("to_object_name"),
            )
            .select_from(
                material_movements.outerjoin(construction_sections, construction_sections.c.id == material_movements.c.section_id)
                .outerjoin(materials, materials.c.id == material_movements.c.material_id)
                .outerjoin(from_obj, from_obj.c.id == material_movements.c.from_object_id)
                .outerjoin(to_obj, to_obj.c.id == material_movements.c.to_object_id)
            )
            .where(material_movements.c.report_date >= since)
            .order_by(material_movements.c.report_date.desc(), material_movements.c.created_at.desc())
            .limit(300)
        )
        ctx.update(rows=db.execute(stmt).mappings().all(), days=days)
        return templates.TemplateResponse("movements.html", ctx)


@app.get("/equipment", response_class=HTMLResponse)
def equipment_page(request: Request, days: int = 14):
    with SessionLocal() as db:
        ctx = base_context(request, db)
        since = date.today() - timedelta(days=days)
        stmt = (
            select(report_equipment_units, daily_reports.c.report_date, construction_sections.c.name.label("section_name"))
            .select_from(
                report_equipment_units.join(daily_reports, daily_reports.c.id == report_equipment_units.c.daily_report_id)
                .outerjoin(construction_sections, construction_sections.c.id == daily_reports.c.section_id)
            )
            .where(daily_reports.c.report_date >= since)
            .order_by(daily_reports.c.report_date.desc(), report_equipment_units.c.created_at.desc())
            .limit(300)
        )
        ctx.update(rows=db.execute(stmt).mappings().all(), days=days)
        return templates.TemplateResponse("equipment.html", ctx)


@app.get("/analytics", response_class=HTMLResponse)
def analytics_page(request: Request, days: int = 30):
    with SessionLocal() as db:
        ctx = base_context(request, db)
        since = date.today() - timedelta(days=days)
        section_stats = db.execute(
            select(
                construction_sections.c.name.label("section_name"),
                func.count(func.distinct(daily_work_items.c.id)).label("work_items_count"),
                func.count(func.distinct(material_movements.c.id)).label("movements_count"),
                func.count(func.distinct(report_equipment_units.c.id)).label("equipment_count"),
            )
            .select_from(construction_sections)
            .outerjoin(daily_work_items, and_(daily_work_items.c.section_id == construction_sections.c.id, daily_work_items.c.report_date >= since))
            .outerjoin(material_movements, and_(material_movements.c.section_id == construction_sections.c.id, material_movements.c.report_date >= since))
            .outerjoin(daily_reports, and_(daily_reports.c.section_id == construction_sections.c.id, daily_reports.c.report_date >= since))
            .outerjoin(report_equipment_units, report_equipment_units.c.daily_report_id == daily_reports.c.id)
            .group_by(construction_sections.c.name)
            .order_by(construction_sections.c.name)
        ).mappings().all()
        object_stats = db.execute(
            select(
                objects.c.name.label("object_name"),
                func.coalesce(func.sum(project_work_items.c.project_volume), 0).label("project_volume"),
                func.coalesce(func.sum(daily_work_items.c.volume), 0).label("fact_volume"),
            )
            .select_from(objects)
            .outerjoin(project_work_items, project_work_items.c.object_id == objects.c.id)
            .outerjoin(daily_work_items, and_(daily_work_items.c.object_id == objects.c.id, daily_work_items.c.report_date >= since))
            .group_by(objects.c.name)
            .order_by(objects.c.name)
            .limit(100)
        ).mappings().all()
        material_stats = db.execute(
            select(
                materials.c.name.label("material_name"),
                func.count(material_movements.c.id).label("moves_count"),
                func.coalesce(func.sum(material_movements.c.volume), 0).label("volume_sum"),
                func.coalesce(func.sum(material_movements.c.trip_count), 0).label("trip_sum"),
            )
            .select_from(materials.outerjoin(material_movements, and_(material_movements.c.material_id == materials.c.id, material_movements.c.report_date >= since)))
            .group_by(materials.c.name)
            .order_by(materials.c.name)
        ).mappings().all()
        equipment_stats = db.execute(
            select(
                report_equipment_units.c.ownership_type,
                report_equipment_units.c.equipment_type,
                func.count(report_equipment_units.c.id).label("count_total"),
                func.sum(case((report_equipment_units.c.status == 'working', 1), else_=0)).label("working_count"),
                func.sum(case((report_equipment_units.c.status == 'repair', 1), else_=0)).label("repair_count"),
                func.coalesce(func.sum(work_item_equipment_usage.c.worked_volume), 0).label("work_volume"),
                func.coalesce(func.sum(material_movement_equipment_usage.c.worked_volume), 0).label("movement_volume"),
                func.coalesce(func.sum(work_item_equipment_usage.c.trips_count), 0).label("work_trips"),
                func.coalesce(func.sum(material_movement_equipment_usage.c.trips_count), 0).label("movement_trips"),
            )
            .select_from(
                report_equipment_units.join(daily_reports, daily_reports.c.id == report_equipment_units.c.daily_report_id)
                .outerjoin(work_item_equipment_usage, work_item_equipment_usage.c.report_equipment_unit_id == report_equipment_units.c.id)
                .outerjoin(material_movement_equipment_usage, material_movement_equipment_usage.c.report_equipment_unit_id == report_equipment_units.c.id)
            )
            .where(daily_reports.c.report_date >= since)
            .group_by(report_equipment_units.c.ownership_type, report_equipment_units.c.equipment_type)
            .order_by(report_equipment_units.c.ownership_type, report_equipment_units.c.equipment_type)
        ).mappings().all()
        ctx.update(section_stats=section_stats, object_stats=object_stats, material_stats=material_stats, equipment_stats=equipment_stats, days=days)
        return templates.TemplateResponse("analytics.html", ctx)


@app.get("/analytics/pk", response_class=HTMLResponse)
def analytics_pk(request: Request, pk_start: str | None = None, pk_end: str | None = None):
    with SessionLocal() as db:
        ctx = base_context(request, db)
        rows = []
        project_rows = []
        object_rows = []
        if pk_start and pk_end:
            start = to_decimal(pk_start)
            end = to_decimal(pk_end)
            rows = db.execute(
                select(
                    daily_work_item_segments,
                    daily_work_items.c.report_date,
                    daily_work_items.c.work_name_raw,
                    work_types.c.name.label("work_type_name"),
                )
                .select_from(
                    daily_work_item_segments.join(daily_work_items, daily_work_items.c.id == daily_work_item_segments.c.daily_work_item_id)
                    .outerjoin(work_types, work_types.c.id == daily_work_items.c.work_type_id)
                )
                .where(and_(daily_work_item_segments.c.pk_start <= end, daily_work_item_segments.c.pk_end >= start))
                .order_by(daily_work_items.c.report_date.desc())
            ).mappings().all()
            project_rows = db.execute(
                select(project_work_item_segments, project_work_items.c.project_volume, work_types.c.name.label("work_type_name"))
                .select_from(project_work_item_segments.join(project_work_items, project_work_items.c.id == project_work_item_segments.c.project_work_item_id)
                             .outerjoin(work_types, work_types.c.id == project_work_items.c.work_type_id))
                .where(and_(project_work_item_segments.c.pk_start <= end, project_work_item_segments.c.pk_end >= start))
                .order_by(project_work_item_segments.c.pk_start)
            ).mappings().all()
            object_rows = db.execute(
                select(object_segments, objects.c.name.label("object_name"))
                .select_from(object_segments.join(objects, objects.c.id == object_segments.c.object_id))
                .where(and_(object_segments.c.pk_start <= end, object_segments.c.pk_end >= start))
                .order_by(object_segments.c.pk_start)
            ).mappings().all()
        ctx.update(pk_start=pk_start or "", pk_end=pk_end or "", fact_rows=rows, project_rows=project_rows, object_rows=object_rows)
        return templates.TemplateResponse("analytics_pk.html", ctx)


@app.get("/sections", response_class=HTMLResponse)
def sections_page(request: Request):
    with SessionLocal() as db:
        ctx = base_context(request, db)
        rows = db.execute(
            select(construction_sections, construction_section_versions)
            .select_from(construction_sections.outerjoin(construction_section_versions, construction_section_versions.c.section_id == construction_sections.c.id))
            .order_by(construction_sections.c.name, construction_section_versions.c.valid_from.desc())
        ).mappings().all()
        ctx.update(rows=rows)
        return templates.TemplateResponse("sections.html", ctx)


@app.get("/objects", response_class=HTMLResponse)
def objects_page(request: Request):
    with SessionLocal() as db:
        ctx = base_context(request, db)
        rows = db.execute(
            select(objects, object_types.c.name.label("object_type_name"), constructives.c.name.label("constructive_name"))
            .select_from(objects.outerjoin(object_types, object_types.c.id == objects.c.object_type_id).outerjoin(constructives, constructives.c.id == objects.c.constructive_id))
            .order_by(objects.c.name)
        ).mappings().all()
        segments = db.execute(select(object_segments).order_by(object_segments.c.pk_start)).mappings().all()
        grouped = {}
        for seg in segments:
            grouped.setdefault(seg["object_id"], []).append(seg)
        ctx.update(rows=rows, grouped_segments=grouped)
        return templates.TemplateResponse("objects.html", ctx)


@app.get("/project", response_class=HTMLResponse)
def project_page(request: Request):
    with SessionLocal() as db:
        ctx = base_context(request, db)
        rows = db.execute(
            select(project_work_items, objects.c.name.label("object_name"), work_types.c.name.label("work_type_name"), constructives.c.name.label("constructive_name"))
            .select_from(project_work_items.outerjoin(objects, objects.c.id == project_work_items.c.object_id)
                         .outerjoin(work_types, work_types.c.id == project_work_items.c.work_type_id)
                         .outerjoin(constructives, constructives.c.id == project_work_items.c.constructive_id))
            .order_by(objects.c.name, work_types.c.name)
            .limit(500)
        ).mappings().all()
        segs = db.execute(select(project_work_item_segments).order_by(project_work_item_segments.c.pk_start)).mappings().all()
        grouped = {}
        for seg in segs:
            grouped.setdefault(seg["project_work_item_id"], []).append(seg)
        ctx.update(rows=rows, grouped_segments=grouped)
        return templates.TemplateResponse("project.html", ctx)
