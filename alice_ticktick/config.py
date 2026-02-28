from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Конфигурация приложения."""

    ticktick_client_id: str = ""
    ticktick_client_secret: str = ""
    ticktick_v2_enabled: bool = False

    alice_skill_id: str = ""

    yc_folder_id: str = ""
    yc_function_id: str = ""
    yc_service_account_id: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
