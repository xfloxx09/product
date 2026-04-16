from flask import Blueprint, render_template

from ...services.plan_catalog import list_plan_definitions


bp = Blueprint("public", __name__)


@bp.get("/")
def home():
    return render_template("public/home.html")


@bp.get("/pricing")
def pricing():
    plans = list_plan_definitions()
    return render_template("public/pricing.html", plans=plans)
