import csv
from datetime import datetime
import io
import json

from ..extensions import db
from ..models import AgentProfile, CoachingSession, CsvImportRowError, Team


def _first_value(row, aliases):
    for alias in aliases:
        value = row.get(alias)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return ""


def _parse_score(score_raw, transforms):
    if not score_raw:
        return None
    value = str(score_raw).strip()
    if transforms.get("strip_percent", True):
        value = value.replace("%", "")
    if transforms.get("decimal_comma"):
        value = value.replace(",", ".")
    parsed = float(value)
    scale_mode = transforms.get("score_scale", "auto")
    if scale_mode == "0_1":
        parsed = parsed * 100.0
    elif scale_mode == "auto" and 0 <= parsed <= 1:
        parsed = parsed * 100.0
    return round(parsed, 2)


def _parse_occurred_at(date_raw, transforms):
    if not date_raw:
        return None
    value = str(date_raw).strip()
    if not value:
        return None
    explicit_fmt = transforms.get("date_format", "").strip()
    if explicit_fmt:
        return datetime.strptime(value, explicit_fmt)
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def process_csv_rows(
    tenant_id,
    coach_user_id,
    rows,
    mapping,
    transforms=None,
    persist=True,
    active_members_limit=None,
    current_active_members=0,
):
    transforms = transforms or {}
    summary = {
        "created_agents": 0,
        "created_sessions": 0,
        "created_teams": 0,
        "errors": 0,
    }
    errors = []
    known_team_names = set()
    known_agent_codes = set()
    active_members_count = int(current_active_members or 0)

    if not persist:
        known_team_names = {
            name for (name,) in db.session.query(Team.name).filter_by(tenant_id=tenant_id).all()
        }
        known_agent_codes = {
            code
            for (code,) in db.session.query(AgentProfile.employee_code).filter_by(tenant_id=tenant_id).all()
        }

    for idx, row in enumerate(rows, start=2):
        employee_code = _first_value(row, mapping.get("employee_id", []))
        employee_name = _first_value(row, mapping.get("employee_name", []))
        team_name = _first_value(row, mapping.get("team_name", []))
        date_raw = _first_value(row, mapping.get("coaching_date", []))
        coaching_type = _first_value(row, mapping.get("coaching_type", [])) or "quality"
        channel = _first_value(row, mapping.get("channel", [])) or "call"
        score_raw = _first_value(row, mapping.get("score", []))
        coach_name = _first_value(row, mapping.get("coach_name", []))

        if not employee_code or not employee_name:
            summary["errors"] += 1
            errors.append((idx, row, "Missing required employee_id or employee_name"))
            continue

        team = None
        if team_name:
            if persist:
                team = Team.query.filter_by(tenant_id=tenant_id, name=team_name).first()
                if not team:
                    team = Team(tenant_id=tenant_id, name=team_name)
                    db.session.add(team)
                    db.session.flush()
                    summary["created_teams"] += 1
            elif team_name not in known_team_names:
                known_team_names.add(team_name)
                summary["created_teams"] += 1

        agent = None
        if persist:
            agent = AgentProfile.query.filter_by(tenant_id=tenant_id, employee_code=employee_code).first()
            if not agent:
                if active_members_limit is not None and active_members_count >= int(active_members_limit):
                    summary["errors"] += 1
                    errors.append(
                        (
                            idx,
                            row,
                            f"Active member limit reached ({active_members_limit}); cannot create more members.",
                        )
                    )
                    continue
                agent = AgentProfile(
                    tenant_id=tenant_id,
                    employee_code=employee_code,
                    full_name=employee_name,
                    team_id=team.id if team else None,
                )
                db.session.add(agent)
                db.session.flush()
                summary["created_agents"] += 1
                active_members_count += 1
        elif employee_code not in known_agent_codes:
            if active_members_limit is not None and active_members_count >= int(active_members_limit):
                summary["errors"] += 1
                errors.append(
                    (
                        idx,
                        row,
                        f"Active member limit reached ({active_members_limit}); cannot create more members.",
                    )
                )
                continue
            known_agent_codes.add(employee_code)
            summary["created_agents"] += 1
            active_members_count += 1

        score = None
        if score_raw:
            try:
                score = _parse_score(score_raw, transforms)
            except ValueError:
                summary["errors"] += 1
                errors.append((idx, row, f"Invalid score '{score_raw}'"))
                continue

        occurred_at = None
        if date_raw:
            occurred_at = _parse_occurred_at(date_raw, transforms)
            if occurred_at is None:
                summary["errors"] += 1
                errors.append((idx, row, f"Invalid coaching_date '{date_raw}'"))
                continue

        summary["created_sessions"] += 1
        if persist:
            # Imported records may not know exact coach user yet; store in notes for traceability.
            session = CoachingSession(
                tenant_id=tenant_id,
                agent_id=agent.id,
                coach_user_id=coach_user_id,
                coaching_type=coaching_type,
                channel=channel,
                score=score,
                occurred_at=occurred_at or datetime.utcnow(),
                notes=f"Imported coach field: {coach_name}" if coach_name else "Imported CSV session",
            )
            db.session.add(session)

    return summary, errors


def read_csv_upload(file_storage):
    content = file_storage.read()
    return read_csv_bytes(content)


def read_csv_bytes(content):
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        decoded = content.decode("latin-1")
    return read_csv_text(decoded)


def read_csv_text(decoded):
    stream = io.StringIO(decoded)
    reader = csv.DictReader(stream)
    return list(reader), list(reader.fieldnames or [])


def persist_import_errors(import_job, errors):
    rows = []
    for row_number, payload, message in errors:
        rows.append(
            CsvImportRowError(
                import_job_id=import_job.id,
                row_number=row_number,
                row_payload_json=json.dumps(payload),
                error_message=message,
            )
        )
    return rows
