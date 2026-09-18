"""A request that never finishes must end at the deadline, not hold the worker."""

import socket
import threading
import time

import pytest
import sec_2016 as s

FORM = b'<html><input type="hidden" name="__VIEWSTATE" value="x"></html>'


def dribbling_server(stop, sent):
    """Answers with headers, then one body byte every 50ms and never the rest."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    def serve():
        while not stop.is_set():
            listener.settimeout(0.2)
            try:
                connection, _ = listener.accept()
            except TimeoutError:
                continue
            connection.recv(65536)
            connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 100000000\r\n\r\n")
            while not stop.is_set():
                try:
                    connection.sendall(b"x")
                except OSError:
                    break
                sent.append(1)
                time.sleep(0.05)
            connection.close()
        listener.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{listener.getsockname()[1]}/"


def test_a_dribbled_response_ends_at_the_deadline(monkeypatch):
    stop, sent = threading.Event(), []
    monkeypatch.setattr(s, "URL", dribbling_server(stop, sent))
    monkeypatch.setattr(s, "DEADLINE", 0.5)
    monkeypatch.setattr(s, "RETRY_BUDGET", 0)
    monkeypatch.setattr(s, "LOCAL", threading.local())
    started = time.monotonic()
    try:
        with pytest.raises(s.Transient):
            s.request("GET")
    finally:
        stop.set()
    # The read timeout alone would never fire: bytes keep arriving.
    assert time.monotonic() - started < 10
    assert len(sent) > 1


def test_a_prompt_response_is_returned_and_the_alarm_does_not_fire(monkeypatch):
    stop = threading.Event()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    def serve():
        connection, _ = listener.accept()
        connection.recv(65536)
        connection.sendall(
            b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n%s" % (len(FORM), FORM)
        )
        connection.close()
        listener.close()

    threading.Thread(target=serve, daemon=True).start()
    monkeypatch.setattr(s, "URL", f"http://127.0.0.1:{listener.getsockname()[1]}/")
    monkeypatch.setattr(s, "DEADLINE", 30)
    monkeypatch.setattr(s, "LOCAL", threading.local())
    try:
        assert "__VIEWSTATE" in s.request("GET")
    finally:
        stop.set()
