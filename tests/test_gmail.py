import base64
import unittest
from unittest.mock import patch

from src.agent import gmail
from src.agent.ai import _gmail_query_from_prompt


class GmailTests(unittest.TestCase):
    def test_only_explicit_gmail_requests_trigger_search(self):
        self.assertEqual(
            _gmail_query_from_prompt("Search my Gmail for subject:invoice"),
            "subject:invoice",
        )
        self.assertEqual(
            _gmail_query_from_prompt("Check my unread emails"),
            "in:inbox is:unread",
        )
        self.assertEqual(
            _gmail_query_from_prompt("Check my inbox"),
            "in:inbox newer_than:7d",
        )
        self.assertIsNone(_gmail_query_from_prompt("What should I do today?"))

    def test_decodes_headers_and_plain_text_body(self):
        encoded = base64.urlsafe_b64encode(b"hello").decode().rstrip("=")
        message = {"payload": {
            "headers": [{"name": "Subject", "value": "Test"}],
            "mimeType": "text/plain",
            "body": {"data": encoded},
        }}
        parsed = gmail._record(message)
        self.assertEqual(parsed["subject"], "Test")
        self.assertEqual(parsed["body"], "hello")

    def test_strips_html(self):
        encoded = base64.urlsafe_b64encode(
            b"<p>Hello</p><script>ignore</script><div>world</div>"
        ).decode().rstrip("=")
        self.assertEqual(gmail._body({
            "mimeType": "text/html", "body": {"data": encoded}
        }), "Hello world")

    def test_search_is_capped_and_empty_query_rejected(self):
        with patch.object(gmail, "_service") as factory:
            api = factory.return_value.users.return_value.messages.return_value
            api.list.return_value.execute.return_value = {"messages": []}
            self.assertEqual(gmail.search_messages("in:inbox", 100), [])
            self.assertEqual(api.list.call_args.kwargs["maxResults"], 5)
        with patch.object(gmail, "_service") as factory:
            with self.assertRaises(ValueError):
                gmail.search_messages(" ")
            factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
