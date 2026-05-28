from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str
    openai_api_key: str
    mongodb_uri: str
    mongodb_db_name: str = "aimentor"
    clerk_secret_key: str = ""
    frontend_url: str = "http://localhost:3000"

    class Config:
        env_file = ".env"


settings = Settings()
