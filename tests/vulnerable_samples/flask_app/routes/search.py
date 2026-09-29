"""HTTP layer -- where attacker-controlled input enters the application."""

from flask import Blueprint, jsonify, request

from services.search_service import search_users

search_bp = Blueprint("search", __name__)


@search_bp.route("/search")
def search():
    # SOURCE: fully attacker-controlled query string parameter.
    q = request.args["q"]
    results = search_users(q)
    return jsonify(results)


@search_bp.route("/users/<user_id>")
def get_user(user_id):
    from services.search_service import get_user_by_id

    return jsonify(get_user_by_id(user_id))
