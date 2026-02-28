"""FSM states for multi-step dialogs."""

from aliceio.fsm.state import State, StatesGroup


class DeleteTaskStates(StatesGroup):
    """States for delete task confirmation flow."""

    confirm = State()
