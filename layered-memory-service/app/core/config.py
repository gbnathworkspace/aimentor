import os
import logging
from functools import lru_cache
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

# SSM parameter paths
_SSM_VOYAGE_API_KEY = "voyageapikey"
_SSM_MEMORY_SERVICE_API_KEY = "/layered-memory-service/api-key"


def _is_production() -> bool:
    return os.getenv("APP_ENV", "local").lower() == "production"


def _ssm_get(param_name: str) -> str:
    import boto3
    client = boto3.client("ssm", region_name=os.getenv("AWS_REGION", "ap-south-1"))
    resp = client.get_parameter(Name=param_name, WithDecryption=True)
    return resp["Parameter"]["Value"].strip()


class Settings(BaseSettings):
    mongodb_uri: str
    mongodb_db_name: str = "layered_memory"
    voyage_api_key: str
    memory_service_api_key: str
    anthropic_api_key: str
    log_level: str = "INFO"
    port: int = 8000

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def _load_settings() -> Settings:
    if _is_production():
        logger.info("Production: loading secrets from AWS SSM Parameter Store")
        # DB_SSM_PARAM_NAME is an env var whose value is the SSM path for the MongoDB URI
        # e.g.  DB_SSM_PARAM_NAME=/mentorman/mongodb-uri
        db_ssm_param = os.environ["DB_SSM_PARAM_NAME"]
        return Settings(
            mongodb_uri=_ssm_get(db_ssm_param),
            mongodb_db_name=os.getenv("MONGODB_DB_NAME", "layered_memory"),
            voyage_api_key=_ssm_get(_SSM_VOYAGE_API_KEY),
            memory_service_api_key=_ssm_get(_SSM_MEMORY_SERVICE_API_KEY),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            port=int(os.getenv("PORT", "8000")),
        )

    logger.info("Local: loading secrets from .env")
    return Settings()


settings = _load_settings()
