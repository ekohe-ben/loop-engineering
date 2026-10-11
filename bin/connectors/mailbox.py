#!/usr/bin/env python3
"""Mailbox connector. Accounts are managed on the Inbox Triage page; this
type only reports whether a refresh token is stored for the inbox."""
import i18n
from connectors import register
from connectors.base import Connector, ConnectorError, MAIL


@register
class MailboxConnector(Connector):
    type = "mailbox"
    label = "Mailbox"
    icon = "mail"
    capabilities = frozenset({MAIL})
    fields = ()
    secret_label = None
    external = True
    category = "mail"
    description = "Gmail or Outlook inbox managed on the Inbox Triage page."

    def test(self):
        try:
            import mail_auth
            token = mail_auth.keychain_get(self.account["id"])
        except Exception as exc:  # noqa: BLE001 - test() must never raise
            return False, i18n.t("{kind}: {detail}", kind=type(exc).__name__, detail=exc)
        if token is None:
            return False, i18n.t("Not authorized - finish setup on the Inbox Triage page")
        return True, i18n.t("Authorized")

    def __init__(self, account, secret=None, http=None, inbox_fn=None, token_fn=None, provider_factory=None):
        super().__init__(account, secret=secret, http=http)
        self._inbox_fn, self._token_fn, self._provider_factory = inbox_fn, token_fn, provider_factory

    def _provider(self):
        """Read-only mail provider for this inbox. Raises ConnectorError with a
        token-free message (the exception text of auth failures names no token)."""
        import inbox_config
        import mail_auth
        import mail_http
        import mail_providers
        inbox_fn = self._inbox_fn or inbox_config.get_inbox
        token_fn = self._token_fn or mail_auth.get_access_token
        factory = self._provider_factory or mail_providers.get_provider
        try:
            inbox = inbox_fn(self.account["id"])
            token = token_fn(inbox)
            return factory(inbox, token, lambda: token_fn(inbox))
        except (mail_auth.ReauthRequired, mail_http.AuthExpired) as exc:
            raise ConnectorError(str(exc) or i18n.t("Sign-in expired - reconnect this inbox")) from None
        except KeyError:
            raise ConnectorError(i18n.t("Mailbox is not configured")) from None
        except mail_auth.KeychainError:
            raise ConnectorError(i18n.t("Could not read the mailbox credentials")) from None

    def _call(self, method, *args):
        import mail_http
        from connectors.base import describe_http_error
        provider = self._provider()
        try:
            return getattr(provider, method)(*args)
        except mail_http.MailHTTPError as exc:
            raise ConnectorError(describe_http_error(exc)) from None

    def search_messages(self, query, limit):
        return self._call("search_messages", query, limit)

    def read_message(self, message_id):
        return self._call("read_message", message_id)
