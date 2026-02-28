from alice_ticktick.config import Settings


def test_default_settings() -> None:
    s = Settings(
        _env_file=None,  # type: ignore[call-arg]
        ticktick_client_id="",
        ticktick_client_secret="",
        alice_skill_id="",
    )
    assert s.ticktick_v2_enabled is False
    assert s.yc_folder_id == ""
    assert s.yc_function_id == ""
    assert s.yc_service_account_id == ""
