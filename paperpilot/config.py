from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mode: Literal["mock", "live"] = Field(default="mock", validation_alias="PAPERPILOT_MODE")
    data_dir: Path = Field(default=Path("data"), validation_alias="PAPERPILOT_DATA_DIR")
    api_key: SecretStr = Field(default=SecretStr(""), validation_alias="OPENAI_API_KEY")
    base_url: str = Field(default="https://api.openai.com/v1", validation_alias="OPENAI_BASE_URL")
    model: str = Field(default="", validation_alias="OPENAI_MODEL")
    model_extra_body: dict = Field(default_factory=dict, validation_alias="PAPERPILOT_MODEL_EXTRA_BODY")

    def prepare(self) -> None:
        self.data_dir = self.data_dir.resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.mode == "live" and (not self.model or not self.api_key.get_secret_value()):
            raise ValueError("live 模式需要 OPENAI_MODEL 和 OPENAI_API_KEY；Ollama 的 key 可填 ollama")
