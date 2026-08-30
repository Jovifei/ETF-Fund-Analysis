"""Explicit persistence policy for bounded, isolated service executions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TaskExecutionPolicy:
    """Controls operational history without suppressing domain calculation rows.

    Formal API/CLI/scheduler flows use the default.  The process-local demo
    runtime opts out of durable task and provider-audit rows so its synthetic
    work can never be presented as operational history.
    """

    persist_task_runs: bool = True
    persist_provider_audits: bool = True

    @classmethod
    def isolated_demo(cls) -> "TaskExecutionPolicy":
        return cls(persist_task_runs=False, persist_provider_audits=False)
