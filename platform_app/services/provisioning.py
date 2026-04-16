import json

from ..extensions import db
from ..models import CsvImportProfile, ScorecardTemplate, Subscription


INDUSTRY_PRESETS = {
    "telecom": {
        "scorecard": {
            "sections": [
                {"name": "Greeting & Compliance", "weight": 20},
                {"name": "Needs Discovery", "weight": 25},
                {"name": "Product Fit", "weight": 30},
                {"name": "Objection Handling", "weight": 25},
            ]
        },
        "csv_mapping": {
            "employee_id": ["agent_id", "employee_id", "ma_kennung"],
            "employee_name": ["agent_name", "full_name", "name"],
            "team_name": ["team", "team_name"],
            "coaching_date": ["date", "coaching_date", "event_date"],
            "score": ["score", "points", "quality_score"],
        },
    },
    "energy": {
        "scorecard": {
            "sections": [
                {"name": "Tariff Accuracy", "weight": 30},
                {"name": "Contract Clarity", "weight": 25},
                {"name": "Compliance", "weight": 25},
                {"name": "Customer Trust", "weight": 20},
            ]
        },
        "csv_mapping": {
            "employee_id": ["berater_id", "employee_id", "agent_id"],
            "employee_name": ["berater_name", "name", "full_name"],
            "team_name": ["team", "unit", "team_name"],
            "coaching_date": ["datum", "date", "coaching_date"],
            "score": ["score", "bewertung", "quality_score"],
        },
    },
    "generic": {
        "scorecard": {"sections": [{"name": "Quality", "weight": 100}]},
        "csv_mapping": {
            "employee_id": ["employee_id"],
            "employee_name": ["employee_name"],
            "team_name": ["team_name"],
            "coaching_date": ["coaching_date"],
            "score": ["score"],
        },
    },
}


def seed_tenant_defaults(tenant):
    preset = INDUSTRY_PRESETS.get(tenant.industry, INDUSTRY_PRESETS["generic"])

    existing_scorecard = ScorecardTemplate.query.filter_by(tenant_id=tenant.id).first()
    if not existing_scorecard:
        db.session.add(
            ScorecardTemplate(
                tenant_id=tenant.id,
                name=f"{tenant.industry.capitalize()} Core Scorecard",
                is_default=True,
                config_json=json.dumps(preset["scorecard"]),
            )
        )

    existing_csv = CsvImportProfile.query.filter_by(tenant_id=tenant.id, is_default=True).first()
    if not existing_csv:
        db.session.add(
            CsvImportProfile(
                tenant_id=tenant.id,
                name="Default Import Mapping",
                is_default=True,
                mapping_json=json.dumps(preset["csv_mapping"]),
            )
        )

    existing_subscription = Subscription.query.filter_by(tenant_id=tenant.id).first()
    if not existing_subscription:
        db.session.add(
            Subscription(
                tenant_id=tenant.id,
                status="trialing",
            )
        )
