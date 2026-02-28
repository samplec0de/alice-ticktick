from alice_ticktick.config import Settings


def test_default_settings() -> None:
    s = Settings(
        ticktick_client_id="",
        ticktick_client_secret="",
        alice_skill_id="",
    )
    assert s.host == "0.0.0.0"
    assert s.port == 8080
    assert s.ticktick_v2_enabled is False
