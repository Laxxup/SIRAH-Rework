from __future__ import annotations

from sirah.core.voice import State, Supervisor


class SpyEyes:
    def __init__(self) -> None:
        self.states: list[State] = []
        self.actions: list[object] = []
        self.closed = False

    def on_state(self, state: State) -> None:
        self.states.append(state)

    def on_actions(self, actions: object) -> None:
        self.actions.append(actions)

    def close(self) -> None:
        self.closed = True


def test_supervisor_notifies_eyes_and_tracks_state() -> None:
    eyes = SpyEyes()
    supervisor = Supervisor(eyes)

    supervisor.set(State.LISTENING)
    supervisor.actions(["{{blink}}"])
    supervisor.set(State.IDLE)
    supervisor.close()

    assert supervisor.state == State.IDLE
    assert eyes.states == [State.LISTENING, State.IDLE]
    assert eyes.actions == [["{{blink}}"]]
    assert eyes.closed is True


def test_supervisor_close_on_null_eyes_does_not_fail() -> None:
    supervisor = Supervisor()
    supervisor.set(State.SPEAKING)
    supervisor.close()
    assert supervisor.state == State.SPEAKING
