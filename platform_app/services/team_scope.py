from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..models import UserTeamScope


def get_user_team_scope_ids(user):
    if not user or not getattr(user, "id", None):
        return None
    try:
        rows = UserTeamScope.query.filter_by(tenant_id=user.tenant_id, user_id=user.id).all()
    except SQLAlchemyError:
        return None
    ids = {row.team_id for row in rows}
    return ids or None


def get_team_scope_map_for_users(tenant_id, user_ids):
    result = {}
    ids = [uid for uid in user_ids if uid]
    if not ids:
        return result
    try:
        rows = UserTeamScope.query.filter(
            UserTeamScope.tenant_id == tenant_id,
            UserTeamScope.user_id.in_(ids),
        ).all()
    except SQLAlchemyError:
        return result
    for row in rows:
        result.setdefault(row.user_id, set()).add(row.team_id)
    return result


def replace_user_team_scope(*, tenant_id, user_id, team_ids):
    clean_ids = sorted({int(tid) for tid in team_ids if str(tid).strip().isdigit()})
    try:
        UserTeamScope.query.filter_by(tenant_id=tenant_id, user_id=user_id).delete(synchronize_session=False)
        for team_id in clean_ids:
            db.session.add(UserTeamScope(tenant_id=tenant_id, user_id=user_id, team_id=team_id))
        return True
    except SQLAlchemyError:
        db.session.rollback()
        return False
