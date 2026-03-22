"""Derives next tasks from a development plan outline.

Support layer only — not agent behavior. Planning semantics live in SKILL.md / prompts.
"""

from __future__ import annotations

from agents.cody.runtime.contracts import TaskItem


def get_next_steps(plan_text: str | None = None) -> list[TaskItem]:
    """
    Return the next tasks implied by an optional plan body.

    When `plan_text` is set, the workflow assumes a document exists to parse.
    When omitted, callers get a generic review-oriented sequence.
    """
    if plan_text:
        return [
            TaskItem(id="p1", title="Parse plan document", description="Extract milestones and dependencies."),
            TaskItem(id="p2", title="Map milestones to tasks", description="Produce actionable work items."),
            TaskItem(id="p3", title="Human review", description="Confirm scope before implementation."),
        ]
    return [
        TaskItem(id="n1", title="Define milestone", description="Name the outcome and constraints."),
        TaskItem(id="n2", title="Enumerate tasks", description="Break work into reviewable units."),
        TaskItem(id="n3", title="Risk review", description="Classify risk before changes."),
        TaskItem(id="n4", title="Human review", description="Approve or revise the plan."),
    ]
