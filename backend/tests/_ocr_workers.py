"""Lightweight spawn targets: child startup must not import the test ORM stack."""
import time


def response_then_sleep_worker(conn, *args) -> None:
    del args
    conn.send({"status": "completed", "lines": []})
    time.sleep(2)
