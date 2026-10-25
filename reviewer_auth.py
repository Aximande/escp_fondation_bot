"""Authorize human reviewers before using the server's Google service account.

Claims must come from Streamlit's OIDC-validated st.user, never request input.
Google service-account credentials are not evidence of a visitor's identity.
"""
import math
import re
import time
from urllib.parse import urlsplit

GOOGLE_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}
GOOGLE_METADATA = "https://accounts.google.com/.well-known/openid-configuration"


def allowed_reviewers(value):
    """Require an explicit, nonempty list of complete email addresses."""
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("Missing reviewer allowlist")
    result = set()
    for email in value:
        if not isinstance(email, str) or not re.fullmatch(r"[^@\s*]+@[^@\s*]+\.[^@\s*]+", email.strip()):
            raise ValueError("Invalid reviewer allowlist")
        result.add(email.strip().casefold())
    return result


def authorized_identity(claims, emails, client_id, now=None):
    """Return a stable identity only for a valid, allowed Google OIDC user."""
    now = time.time() if now is None else now
    if claims.get("is_logged_in") is not True:
        return None
    if claims.get("iss") not in GOOGLE_ISSUERS or claims.get("aud") != client_id:
        return None
    if claims.get("email_verified") is not True:
        return None
    subject = claims.get("sub")
    email = claims.get("email")
    if not isinstance(subject, str) or not subject or not isinstance(email, str):
        return None
    expiry = claims.get("exp")
    issued = claims.get("iat")
    for timestamp in (expiry, issued):
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp):
            return None
    if expiry <= now or issued > now + 60 or issued >= expiry:
        return None
    email = email.strip().casefold()
    if email not in emails:
        return None
    return ("https://accounts.google.com", subject, email)


def clear_reviewer_session(st):
    """Drop cached data and credentials when authorization disappears or changes."""
    # Preserve pending button events so a login click survives the next rerun.
    for key in list(st.session_state):
        if key not in {"reviewer_login", "reviewer_logout"}:
            del st.session_state[key]


def require_reviewer(st, load_service_credentials, now=None):
    """Render login/access errors and return False before any privileged UI runs."""
    try:
        auth = st.secrets["auth"]
        google = auth["google"]
        emails = allowed_reviewers(st.secrets["reviewer_auth"]["allowed_emails"])
        client_id = google["client_id"]
        if not isinstance(client_id, str) or not client_id.endswith('.apps.googleusercontent.com'):
            raise ValueError("Missing OAuth client")
        if google["server_metadata_url"] != GOOGLE_METADATA:
            raise ValueError("Expected Google OIDC")
        cookie_secret = auth["cookie_secret"]
        if not isinstance(cookie_secret, str) or len(cookie_secret) < 32 or cookie_secret.startswith('REPLACE_'):
            raise ValueError("Missing strong cookie secret")
        client_secret = google["client_secret"]
        if not isinstance(client_secret, str) or not client_secret or client_secret.startswith('REPLACE_'):
            raise ValueError("Missing OAuth client secret")
        redirect = urlsplit(auth["redirect_uri"])
        local_http = redirect.scheme == 'http' and redirect.hostname in {'localhost', '127.0.0.1', '::1'}
        if not redirect.hostname or not (redirect.scheme == 'https' or local_http):
            raise ValueError("Expected HTTPS callback, or local HTTP for development")
        if redirect.username or redirect.password or redirect.query or redirect.fragment or not redirect.path.endswith('/oauth2callback'):
            raise ValueError("Invalid OIDC callback")
        claims = st.user.to_dict()
    except Exception:
        clear_reviewer_session(st)
        st.error("La connexion sécurisée n'est pas configurée. Contactez l'administrateur.")
        return False

    identity = authorized_identity(claims, emails, client_id, now=now)
    if identity is None:
        clear_reviewer_session(st)
        if claims.get("is_logged_in") is True:
            st.error("Ce compte n'est pas autorisé ou sa session a expiré.")
            if st.button("Se déconnecter", key="reviewer_logout"):
                st.logout()
        else:
            st.info("Connectez-vous avec votre compte Google de responsable de revue.")
            if st.button("Se connecter avec Google", type="primary", key="reviewer_login"):
                try:
                    st.login("google")
                except Exception:
                    st.error("La connexion a échoué. Réessayez ou contactez l'administrateur.")
        return False

    if st.sidebar.button("Se déconnecter", key="reviewer_logout"):
        clear_reviewer_session(st)
        st.logout()
        return False

    previous = st.session_state.get("reviewer_identity")
    if previous != identity:
        # Do not inherit another user's application data or an old boolean login.
        clear_reviewer_session(st)
        st.session_state["reviewer_identity"] = identity
    st.session_state["authenticated"] = False
    if st.session_state.get("credentials") is None:
        try:
            credentials = load_service_credentials()
            if credentials is None:
                raise ValueError("Missing service credentials")
        except Exception:
            clear_reviewer_session(st)
            st.error("Le service est indisponible. Contactez l'administrateur.")
            return False
        st.session_state["credentials"] = credentials
    st.session_state["authenticated"] = True
    return True
