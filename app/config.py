from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_path: Path = Path("./data/puzzles.sqlite")
    dump_url: str = "https://database.lichess.org/lichess_db_puzzle.csv.zst"
    dump_path: Path = Path("./data/lichess_db_puzzle.csv.zst")


settings = Settings()
