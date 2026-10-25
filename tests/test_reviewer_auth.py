"""Access-control regression tests; no network, Streamlit server or credentials."""
import ast
import copy
from pathlib import Path
import types
import unittest
from unittest.mock import Mock

from reviewer_auth import allowed_reviewers, authorized_identity, require_reviewer

NOW = 1_800_000_000
CLAIMS = {
    "is_logged_in": True,
    "iss": "https://accounts.google.com",
    "aud": "test-client.apps.googleusercontent.com",
    "sub": "stable-user-id",
    "email": "reviewer@example.com",
    "email_verified": True,
    "iat": NOW - 60,
    "exp": NOW + 3600,
}
SECRETS = {
    "auth": {
        "redirect_uri": "http://localhost:8501/oauth2callback",
        "cookie_secret": "a-test-only-cookie-secret-not-used-for-signing",
        "google": {
            "client_id": CLAIMS["aud"],
            "client_secret": "test-only-client-secret",
            "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
        },
    },
    "reviewer_auth": {"allowed_emails": ["reviewer@example.com"]},
}


def fake_streamlit(claims=None):
    user = Mock()
    user.to_dict.return_value = dict(CLAIMS if claims is None else claims)
    return types.SimpleNamespace(
        user=user,
        secrets=copy.deepcopy(SECRETS),
        session_state={},
        sidebar=types.SimpleNamespace(button=Mock(return_value=False)),
        button=Mock(return_value=False),
        error=Mock(), info=Mock(), login=Mock(), logout=Mock(),
    )


class ReviewerAuthorizationTests(unittest.TestCase):
    def test_allowed_reviewer_loads_credentials_only_after_identity_check(self):
        st = fake_streamlit()
        credentials = object()
        load = Mock(return_value=credentials)
        self.assertTrue(require_reviewer(st, load, now=NOW))
        self.assertIs(st.session_state['credentials'], credentials)
        load.assert_called_once_with()
        self.assertTrue(require_reviewer(st, load, now=NOW))
        load.assert_called_once_with()

    def test_old_boolean_cannot_bypass_login(self):
        st = fake_streamlit({'is_logged_in': False})
        st.session_state.update(authenticated=True, credentials=object(), sheet_data=['private'])
        load = Mock()
        self.assertFalse(require_reviewer(st, load, now=NOW))
        self.assertEqual(st.session_state, {})
        load.assert_not_called()

    def test_login_click_only_starts_oidc(self):
        st = fake_streamlit({'is_logged_in': False})
        st.button.return_value = True
        load = Mock()
        self.assertFalse(require_reviewer(st, load, now=NOW))
        st.login.assert_called_once_with('google')
        load.assert_not_called()

    def test_pending_login_click_survives_clearing_private_state(self):
        st = fake_streamlit({'is_logged_in': False})
        st.session_state.update(reviewer_login=True, credentials=object(), sheet_data=['private'])
        st.button.side_effect = lambda *args, **kwargs: st.session_state.get(kwargs['key'], False)
        load = Mock()
        self.assertFalse(require_reviewer(st, load, now=NOW))
        st.login.assert_called_once_with('google')
        self.assertEqual(st.session_state, {'reviewer_login': True})
        load.assert_not_called()

    def test_invalid_claims_do_not_reach_service_account(self):
        cases = [
            {'email': 'outsider@example.com'}, {'email': 'reviewer@example.com.evil.test'},
            {'email_verified': False}, {'email_verified': 'true'},
            {'iss': 'https://attacker.example'}, {'aud': 'another-client'},
            {'sub': ''}, {'sub': None}, {'exp': NOW}, {'exp': NOW - 1},
            {'exp': None}, {'exp': float('nan')}, {'exp': float('inf')},
            {'iat': NOW + 61}, {'iat': None}, {'is_logged_in': 'true'},
        ]
        for changed in cases:
            with self.subTest(changed=changed):
                st = fake_streamlit({**CLAIMS, **changed})
                st.session_state.update(authenticated=True, credentials=object(), sheet_data=['private'])
                load = Mock()
                self.assertFalse(require_reviewer(st, load, now=NOW))
                self.assertEqual(st.session_state, {})
                load.assert_not_called()

    def test_configuration_errors_fail_closed(self):
        cases = [{}, {'reviewer_auth': {'allowed_emails': []}}, copy.deepcopy(SECRETS)]
        cases[-1]['auth']['google']['server_metadata_url'] = 'https://attacker.example'
        for field, value in [('cookie_secret', 'short'), ('cookie_secret', 'REPLACE_WITH_A_LONG_RANDOM_SECRET'),
                             ('redirect_uri', 'http://public.example.com/oauth2callback'),
                             ('redirect_uri', 'https://app.example.com/wrong-callback')]:
            broken = copy.deepcopy(SECRETS)
            broken['auth'][field] = value
            cases.append(broken)
        for secrets in cases:
            with self.subTest(secrets=secrets):
                st = fake_streamlit()
                st.secrets = secrets
                st.session_state['credentials'] = object()
                load = Mock()
                self.assertFalse(require_reviewer(st, load, now=NOW))
                self.assertEqual(st.session_state, {})
                load.assert_not_called()

    def test_allowlist_is_explicit_and_case_normalized(self):
        self.assertEqual(allowed_reviewers([' Reviewer@Example.COM ']), {'reviewer@example.com'})
        for bad in [None, [], 'reviewer@example.com', ['*@example.com'], ['example.com'], [False]]:
            with self.subTest(value=bad), self.assertRaises(ValueError):
                allowed_reviewers(bad)

    def test_identity_change_drops_previous_users_data(self):
        st = fake_streamlit()
        st.session_state.update(reviewer_identity=('old', 'old', 'other@example.com'), credentials=object(), sheet_data=['private'])
        load = Mock(return_value=object())
        self.assertTrue(require_reviewer(st, load, now=NOW))
        self.assertNotIn('sheet_data', st.session_state)
        load.assert_called_once_with()

    def test_allowlist_revocation_is_checked_on_every_rerun(self):
        st = fake_streamlit()
        load = Mock(return_value=object())
        self.assertTrue(require_reviewer(st, load, now=NOW))
        st.secrets['reviewer_auth']['allowed_emails'] = ['someone-else@example.com']
        self.assertFalse(require_reviewer(st, load, now=NOW))
        self.assertEqual(st.session_state, {})
        load.assert_called_once_with()

    def test_expired_session_cannot_reuse_cached_credentials(self):
        st = fake_streamlit()
        load = Mock(return_value=object())
        self.assertTrue(require_reviewer(st, load, now=NOW))
        self.assertFalse(require_reviewer(st, load, now=NOW + 3600))
        self.assertEqual(st.session_state, {})
        load.assert_called_once_with()

    def test_logout_clears_cached_data_before_any_credential_load(self):
        st = fake_streamlit()
        st.sidebar.button.return_value = True
        st.session_state.update(credentials=object(), sheet_data=['private'])
        load = Mock()
        self.assertFalse(require_reviewer(st, load, now=NOW))
        self.assertEqual(st.session_state, {})
        st.logout.assert_called_once_with()
        load.assert_not_called()

    def test_service_failure_does_not_leak_exception_or_authorize(self):
        st = fake_streamlit()
        load = Mock(side_effect=RuntimeError('credential-bearing private exception'))
        self.assertFalse(require_reviewer(st, load, now=NOW))
        self.assertEqual(st.session_state, {})
        self.assertNotIn('private exception', str(st.error.call_args))

    def test_main_entrypoint_checks_access_before_any_application_ui(self):
        # Compile only the reviewed entry function, without application imports.
        source = (Path(__file__).parents[1] / 'streamlit_app.py').read_text()
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'main_app')
        module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
        guard = Mock(return_value=False)
        initialize = Mock()
        processing = Mock()
        main_ui = Mock()
        namespace = {'st': fake_streamlit(), 'google_clients': types.SimpleNamespace(get_google_credentials=Mock()),
                     'require_reviewer': guard, 'initialize_session_state': initialize,
                     'processing_interface': processing, 'main_interface': main_ui}
        exec(compile(module, 'main_app_only', 'exec'), namespace)
        namespace['main_app']()
        guard.assert_called_once()
        initialize.assert_not_called()
        processing.assert_not_called()
        main_ui.assert_not_called()


if __name__ == '__main__':
    unittest.main()
