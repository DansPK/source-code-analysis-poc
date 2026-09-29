"""Service layer -- passes the value through without sanitizing it."""

from database.user_repository import find_user_by_id, search_users_by_name


def search_users(query):
    # No validation or escaping happens here; the value is forwarded as-is.
    return search_users_by_name(query)


def get_user_by_id(user_id):
    return find_user_by_id(user_id)
