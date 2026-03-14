import secrets


def generate_csrf_token():
    return secrets.token_urlsafe(32)
