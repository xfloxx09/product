from dataclasses import dataclass


CASE_STATE_TRANSITIONS = {
    "open": {"planned", "in_progress", "completed", "cancelled"},
    "planned": {"in_progress", "completed", "cancelled"},
    "in_progress": {"follow_up", "completed", "cancelled"},
    "follow_up": {"in_progress", "completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}

SESSION_STATE_TRANSITIONS = {
    "draft": {"submitted", "cancelled"},
    "submitted": {"reviewed"},
    "reviewed": {"locked"},
    "locked": set(),
    "cancelled": set(),
}

ACTION_ITEM_TRANSITIONS = {
    "open": {"blocked", "completed"},
    "blocked": {"open", "completed"},
    "completed": {"open"},
}


def can_transition(state_map, current_state, target_state):
    current = (current_state or "").strip().lower()
    target = (target_state or "").strip().lower()
    return target in state_map.get(current, set())


@dataclass(frozen=True)
class CoachingContract:
    tenant_id: int
    actor_user_id: int
    permission: str

