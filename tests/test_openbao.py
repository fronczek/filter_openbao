import io
import sys
import types
import unittest
from unittest import mock
from urllib import error as urlerror


try:
    from ansible.errors import AnsibleFilterError
except ImportError:
    ansible = types.ModuleType("ansible")
    errors = types.ModuleType("ansible.errors")

    class AnsibleFilterError(Exception):
        pass

    errors.AnsibleFilterError = AnsibleFilterError
    ansible.errors = errors
    sys.modules["ansible"] = ansible
    sys.modules["ansible.errors"] = errors

import openbao


class OpenBaoFilterTests(unittest.TestCase):
    def setUp(self):
        self.connection = {
            "addr": "https://bao.example.com",
            "token": "test-token",
        }

    @mock.patch("openbao._api_get_json")
    def test_kv_v2_uses_data_endpoint_and_requested_version(self, api_get):
        api_get.return_value = {
            "data": {"data": {"password": "secret"}, "metadata": {"version": 3}}
        }

        result = openbao.openbao(
            "kv/app/db", "password", version=3, **self.connection
        )

        self.assertEqual(result, "secret")
        self.assertEqual(
            api_get.call_args.args[0],
            "https://bao.example.com/v1/kv/data/app/db?version=3",
        )

    @mock.patch("openbao._api_get_json")
    def test_kv_v1_uses_exact_path_and_preserves_data_key(self, api_get):
        api_get.return_value = {
            "data": {"data": {"nested": "value"}, "other": "preserved"}
        }

        result = openbao.openbao(
            "app/db", "other", kv_version=1, **self.connection
        )

        self.assertEqual(result, "preserved")
        self.assertEqual(
            api_get.call_args.args[0], "https://bao.example.com/v1/kv/app/db"
        )

    @mock.patch("openbao._api_get_json")
    def test_reads_are_not_cached(self, api_get):
        api_get.side_effect = [
            {"data": {"data": {"password": "first"}}},
            {"data": {"data": {"password": "rotated"}}},
        ]

        first = openbao.openbao("app/db", "password", **self.connection)
        second = openbao.openbao("app/db", "password", **self.connection)

        self.assertEqual((first, second), ("first", "rotated"))
        self.assertEqual(api_get.call_count, 2)

    @mock.patch("openbao._api_get_json")
    def test_version_is_rejected_for_kv_v1(self, api_get):
        with self.assertRaisesRegex(AnsibleFilterError, "only supported for KV v2"):
            openbao.openbao(
                "app/db", version=2, kv_version=1, **self.connection
            )
        api_get.assert_not_called()

    def test_non_object_response_raises_filter_error(self):
        with self.assertRaisesRegex(AnsibleFilterError, "not a JSON object"):
            openbao._extract_secret([], 2)

    def test_invalid_timeout_raises_filter_error(self):
        with self.assertRaisesRegex(AnsibleFilterError, "positive number"):
            openbao.openbao("app/db", timeout="not-a-number", **self.connection)

    def test_boolean_kv_version_is_rejected(self):
        with self.assertRaisesRegex(AnsibleFilterError, "must be 1 or 2"):
            openbao.openbao("app/db", kv_version=True, **self.connection)

    @mock.patch("openbao._api_get_json")
    def test_nested_mount_path_keeps_path_separators(self, api_get):
        api_get.return_value = {"data": {"data": {"password": "secret"}}}

        result = openbao.openbao(
            "team/kv/app/db",
            "password",
            mount_point="team/kv",
            **self.connection,
        )

        self.assertEqual(result, "secret")
        self.assertEqual(
            api_get.call_args.args[0],
            "https://bao.example.com/v1/team/kv/data/app/db",
        )

    @mock.patch("openbao.urlrequest.urlopen")
    def test_unexpected_json_http_error_is_wrapped(self, urlopen):
        urlopen.side_effect = urlerror.HTTPError(
            "https://bao.example.com/v1/kv/data/app/db",
            500,
            "Server Error",
            {},
            io.BytesIO(b"[]"),
        )

        with self.assertRaisesRegex(AnsibleFilterError, "OpenBao API 500"):
            openbao._api_get_json(
                "https://bao.example.com/v1/kv/data/app/db", {}, 10
            )


if __name__ == "__main__":
    unittest.main()
