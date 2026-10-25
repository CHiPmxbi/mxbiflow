import unittest
from unittest.mock import Mock, patch

from mxbiflow.infra.notify import MAX_BODY_BYTES, fit_body, notify


class FitBodyTests(unittest.TestCase):
    def test_short_body_is_unchanged(self) -> None:
        self.assertEqual(fit_body("hello"), "hello")

    def test_long_body_is_cut_to_the_byte_limit(self) -> None:
        body = "猴" * MAX_BODY_BYTES

        fitted = fit_body(body)

        self.assertLessEqual(len(fitted.encode()), MAX_BODY_BYTES)
        self.assertTrue(fitted.endswith("\n[truncated]"))
        self.assertTrue(body.startswith(fitted.removesuffix("\n[truncated]")))


class NotifyTests(unittest.TestCase):
    @patch("mxbiflow.infra.notify.Client")
    def test_sends_fitted_body_with_severity(self, client_cls: Mock) -> None:
        client = client_cls.return_value.__enter__.return_value

        notify("subject", "x" * (MAX_BODY_BYTES + 1), severity="critical")

        subject, body = client.notify.call_args.args
        self.assertEqual(subject, "subject")
        self.assertLessEqual(len(body.encode()), MAX_BODY_BYTES)
        self.assertEqual(client.notify.call_args.kwargs, {"severity": "critical"})


if __name__ == "__main__":
    unittest.main()
