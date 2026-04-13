AUDIT_BARE_EXCEPT = """def fetch_user(db, user_id):
    try:
        return db.query(user_id)
    except:
        pass
"""

AUDIT_HARDCODED_SECRET = """API_KEY = \"sk-live-demo-token\"


def build_headers():
    return {\"Authorization\": f\"Bearer {API_KEY}\"}
"""

AUDIT_CLEAN_FUNCTION = """def add(a: int, b: int) -> int:
    return a + b
"""

FIX_BARE_EXCEPT_ORIGINAL = AUDIT_BARE_EXCEPT

FIX_SECRET_ORIGINAL = """PAYMENTS_API_KEY = \"super-secret-token\"


def build_headers():
    return {\"Authorization\": f\"Bearer {PAYMENTS_API_KEY}\"}
"""

VALIDATION_APPROVED_PATCH = """def fetch_user(db, user_id):
    try:
        return db.query(user_id)
    except Exception as exc:
        raise RuntimeError(f\"failed to fetch {user_id}\") from exc
"""

VALIDATION_SCOPE_DRIFT_PATCH = """def fetch_user(db, user_id):
    try:
        return db.query(user_id)
    except Exception as exc:
        raise RuntimeError(f\"failed to fetch {user_id}\") from exc


def unrelated_helper(flag: bool) -> str:
    return \"changed\" if flag else \"unchanged\"
"""