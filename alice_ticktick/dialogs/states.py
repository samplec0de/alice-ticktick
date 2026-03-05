"""FSM states for multi-step dialogs."""

from aliceio.fsm.state import State, StatesGroup


class DeleteTaskStates(StatesGroup):
    """States for delete task confirmation flow."""

    confirm = State()


class CompleteTaskStates(StatesGroup):
    """States for complete task confirmation flow (low fuzzy score)."""

    confirm = State()


class EditTaskStates(StatesGroup):
    """States for edit task confirmation flow (low fuzzy score)."""

    confirm = State()
