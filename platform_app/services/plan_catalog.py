import copy
import json

from sqlalchemy.exc import SQLAlchemyError

from ..models import AgentProfile
from ..models import PlanDefinition


PLAN_CATALOG = {
    "starter": {
        "id": "starter",
        "name": "Starter",
        "price": "99 EUR",
        "limits": {
            "active_members": 50,
        },
        "features": {
            "source_csv_upload": True,
            "source_sftp": False,
            "source_api": False,
            "alert_analytics": True,
            "advanced_alert_workflows": False,
        },
    },
    "growth": {
        "id": "growth",
        "name": "Growth",
        "price": "249 EUR",
        "limits": {
            "active_members": 300,
        },
        "features": {
            "source_csv_upload": True,
            "source_sftp": True,
            "source_api": True,
            "alert_analytics": True,
            "advanced_alert_workflows": True,
        },
    },
    "enterprise": {
        "id": "enterprise",
        "name": "Enterprise",
        "price": "Custom",
        "limits": {
            "active_members": None,
        },
        "features": {
            "source_csv_upload": True,
            "source_sftp": True,
            "source_api": True,
            "alert_analytics": True,
            "advanced_alert_workflows": True,
        },
    },
}


def _resolved_catalog():
    catalog = copy.deepcopy(PLAN_CATALOG)
    try:
        overrides = PlanDefinition.query.all()
    except SQLAlchemyError:
        # Backward compatibility when DB migration for this table is not applied yet.
        return catalog

    for row in overrides:
        plan_id = (row.plan_id or "").strip().lower()
        if plan_id not in catalog:
            continue
        try:
            cfg = json.loads(row.config_json or "{}")
        except ValueError:
            cfg = {}

        if "name" in cfg and str(cfg["name"]).strip():
            catalog[plan_id]["name"] = str(cfg["name"]).strip()
        if "price" in cfg and str(cfg["price"]).strip():
            catalog[plan_id]["price"] = str(cfg["price"]).strip()

        limits = cfg.get("limits") or {}
        if "active_members" in limits:
            value = limits.get("active_members")
            if value in ("", None):
                catalog[plan_id]["limits"]["active_members"] = None
            else:
                try:
                    parsed = int(value)
                    catalog[plan_id]["limits"]["active_members"] = max(1, parsed)
                except (TypeError, ValueError):
                    pass

        features = cfg.get("features") or {}
        for feature_name in list(catalog[plan_id]["features"].keys()):
            if feature_name in features:
                catalog[plan_id]["features"][feature_name] = bool(features[feature_name])

    return catalog


def list_plan_definitions():
    catalog = _resolved_catalog()
    return [catalog["starter"], catalog["growth"], catalog["enterprise"]]


def normalize_plan(plan):
    plan_id = (plan or "starter").strip().lower()
    if plan_id not in PLAN_CATALOG:
        return "starter"
    return plan_id


def get_plan_definition(plan):
    catalog = _resolved_catalog()
    return catalog[normalize_plan(plan)]


def is_feature_enabled(plan, feature_name):
    plan_def = get_plan_definition(plan)
    return bool(plan_def.get("features", {}).get(feature_name, False))


def get_limit(plan, resource_name):
    plan_def = get_plan_definition(plan)
    return plan_def.get("limits", {}).get(resource_name)


def build_usage_snapshot(tenant):
    active_members_count = AgentProfile.query.filter_by(tenant_id=tenant.id, status="active").count()
    return {
        "active_members": active_members_count,
    }


def evaluate_limit(plan, resource_name, current_count):
    limit = get_limit(plan, resource_name)
    if limit is None:
        return {
            "allowed": True,
            "limit": None,
            "current": current_count,
            "remaining": None,
            "usage_pct": 0.0,
        }
    remaining = max(0, int(limit) - int(current_count))
    usage_pct = round((int(current_count) / int(limit)) * 100, 1) if int(limit) > 0 else 0.0
    return {
        "allowed": int(current_count) < int(limit),
        "limit": int(limit),
        "current": int(current_count),
        "remaining": remaining,
        "usage_pct": usage_pct,
    }
