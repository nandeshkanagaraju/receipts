"""D9 — the suite makes zero network calls."""

from __future__ import annotations

import socket

import pytest


def test_socket_guard_active(network_error: type[Exception]) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(network_error):
        s.connect(("example.invalid", 80))
    s.close()
    print("\nD9: socket.connect blocked")


def test_socket_guard_blocks_create_connection(network_error: type[Exception]) -> None:
    with pytest.raises(network_error):
        socket.create_connection(("example.invalid", 80), timeout=0.01)
    print("D9: socket.create_connection blocked")


def test_socket_guard_blocks_dns(network_error: type[Exception]) -> None:
    with pytest.raises(network_error):
        socket.getaddrinfo("example.invalid", 80)
    print("D9: socket.getaddrinfo blocked")
