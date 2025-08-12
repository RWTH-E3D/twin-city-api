from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # Application Settings
    APP_NAME: str = "Twin City API"
    API_VERSION: str = "1.0.0"
    BASE_PATH: str = "http://localhost:8000"

    COLLECTIONS_BASE_DIR: Path = Path("collections")
    LOADED_COLLECTIONS_DIR: Path = COLLECTIONS_BASE_DIR / "loadedCollections"
    IMPORTED_COLLECTIONS_DIR: Path = COLLECTIONS_BASE_DIR / "imported"
    UPLOADED_COLLECTIONS_DIR: Path = COLLECTIONS_BASE_DIR / "uploaded"

    # API Settings
    DEFAULT_ITEMS_LIMIT: int = 100
    MAX_ITEMS_LIMIT: int = 1000

    # Logging Settings
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_DIR: Path = Path("logs")
    LOG_FILENAME: str = "app.log"
    LOG_ROTATION_SIZE: int = 10 * 1024 * 1024  # 10MB
    LOG_BACKUP_COUNT: int = 5

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "env_prefix": "API_",
    }

    def create_directories(self):
        """Create necessary directories if they don't exist"""
        for directory in [
            self.COLLECTIONS_BASE_DIR,
            self.LOADED_COLLECTIONS_DIR,
            self.IMPORTED_COLLECTIONS_DIR,
            self.UPLOADED_COLLECTIONS_DIR,
            self.LOG_DIR,
        ]:
            directory.mkdir(parents=True, exist_ok=True)


# Create global settings instance
settings = Settings()

# Ensure directories exist
settings.create_directories()
