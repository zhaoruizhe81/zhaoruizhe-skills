from __future__ import annotations

import sys
import unittest

from tests import support  # noqa: F401  (sys.path setup)

import socket

import paramiko  # noqa: F401  确保依赖在测试环境存在

from paramiko_client import (
    _connect_timeouts,
    classify_transport_exception,
    enable_keepalive,
)
import ssh_execute
import ssh_skill


class ConnectTimeoutTests(unittest.TestCase):
    def test_slow_banner_host_gets_wide_timeouts(self):
        values = _connect_timeouts(30)
        self.assertGreaterEqual(values["banner_timeout"], 60)
        self.assertGreaterEqual(values["auth_timeout"], 60)

    def test_invalid_timeout_stays_safe(self):
        values = _connect_timeouts(None)
        self.assertGreaterEqual(values["banner_timeout"], 60)


class KeepaliveTests(unittest.TestCase):
    def test_keepalive_is_enabled_on_transport(self):
        class FakeTransport:
            def __init__(self):
                self.interval = None

            def set_keepalive(self, interval):
                self.interval = interval

        class FakeClient:
            def __init__(self):
                self.transport = FakeTransport()

            def get_transport(self):
                return self.transport

        client = FakeClient()
        enable_keepalive(client, 30)
        self.assertEqual(30, client.transport.interval)

    def test_keepalive_swallows_missing_transport(self):
        class FakeClient:
            def get_transport(self):
                return None

        enable_keepalive(FakeClient())  # 不应抛异常


class TransportExceptionClassificationTests(unittest.TestCase):
    def test_timeout_is_command_timeout(self):
        error_code, outcome, _ = classify_transport_exception(socket.timeout())
        self.assertEqual("command_timeout", error_code)
        self.assertEqual("unknown", outcome)

    def test_eof_maps_to_connection_closed(self):
        error_code, outcome, _ = classify_transport_exception(EOFError())
        self.assertEqual("connection_closed_mid_command", error_code)
        self.assertEqual("unknown", outcome)

    def test_socket_error_maps_to_connection_closed(self):
        error_code, _, _ = classify_transport_exception(ConnectionResetError())
        self.assertEqual("connection_closed_mid_command", error_code)

    def test_paramiko_socket_closed_maps_to_connection_closed(self):
        from paramiko.ssh_exception import SSHException

        error_code, _, _ = classify_transport_exception(SSHException("Socket is closed"))
        self.assertEqual("connection_closed_mid_command", error_code)

    def test_other_exceptions_are_unclassified(self):
        self.assertIsNone(classify_transport_exception(ValueError("boom")))


class ExecContractTests(unittest.TestCase):
    def test_exec_accepts_no_progress_flag(self):
        args = ssh_skill.build_parser().parse_args(
            ["exec", "some-alias", "uptime", "--no-progress"]
        )
        self.assertFalse(args.progress)

    def test_exec_default_timeout_is_generous(self):
        args = ssh_skill.build_parser().parse_args(["exec", "some-alias", "uptime"])
        self.assertEqual(300, args.timeout)

    def test_run_exec_default_timeout_matches_cli(self):
        import inspect

        signature = inspect.signature(ssh_execute.run_exec)
        self.assertEqual(300, signature.parameters["timeout"].default)


class OpensshFailureClassificationTests(unittest.TestCase):
    """openssh_transport 对"远端掐断连接"的识别（shutdown/reboot 场景）"""

    @staticmethod
    def _result(returncode: int, stderr: bytes):
        import subprocess

        from openssh_transport import TransportResult

        return TransportResult.from_completed_process(
            subprocess.CompletedProcess(["ssh"], returncode, stdout=b"", stderr=stderr)
        )

    def test_connection_closed_maps_to_unknown(self):
        result = self._result(255, b"Connection to 192.168.1.142 closed by remote host.")
        self.assertEqual("connection_closed_mid_command", result.error_code)
        self.assertEqual("unknown", result.outcome)

    def test_permission_denied_stays_failed(self):
        result = self._result(255, b"Permission denied (publickey,password).")
        self.assertEqual("remote_command_failed", result.error_code)
        self.assertEqual("failed", result.outcome)

    def test_remote_command_exit_keeps_failed(self):
        result = self._result(1, b"grep: connection closed by pattern not found")
        self.assertEqual("remote_command_failed", result.error_code)
        self.assertEqual("failed", result.outcome)

    def test_reset_by_peer_maps_to_unknown(self):
        result = self._result(255, b"Read from socket failed: Connection reset by peer")
        self.assertEqual("connection_closed_mid_command", result.error_code)


if __name__ == "__main__":
    unittest.main()
