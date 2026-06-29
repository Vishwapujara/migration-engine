from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Groq
    groq_api_key: str = Field(..., env="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", env="GROQ_MODEL")

    # FastAPI
    api_host: str = Field(default="0.0.0.0", env="API_HOST")
    api_port: int = Field(default=8000, env="API_PORT")

    # GitHub
    github_token: str = Field(default="", env="GITHUB_TOKEN")

    # Workspace
    workspace_dir: Path = Field(default=Path("./workspace"), env="WORKSPACE_DIR")

    # Migration limits
    max_self_correction_retries: int = Field(default=3, env="MAX_SELF_CORRECTION_RETRIES")
    max_file_size_kb: int = Field(default=500, env="MAX_FILE_SIZE_KB")
    max_files_for_migration: int = Field(default=200, env="MAX_FILES_FOR_MIGRATION")

    model_config = {
        # Look in the parent dir first (project root when uvicorn runs from backend/),
        # then local backend/.env for any overrides.
        "env_file": ["../.env", ".env"],
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def model_post_init(self, __context) -> None:
        self.workspace_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()

# Supported language pairs
SUPPORTED_MIGRATIONS = {
    ("python", "javascript"),
    ("javascript", "python"),
    ("javascript", "typescript"),
}

# File extensions per language
LANGUAGE_EXTENSIONS: dict[str, list[str]] = {
    "python": [".py"],
    "javascript": [".js", ".jsx", ".mjs", ".cjs"],
    "typescript": [".ts", ".tsx"],
}

# Extensions to skip during migration
SKIP_EXTENSIONS = {
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".md", ".txt",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2",
    ".ttf", ".eot", ".css", ".scss", ".less", ".html", ".lock",
    ".gitignore", ".gitattributes", ".editorconfig", ".prettierrc",
    ".eslintrc", ".babelrc",
}

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".pytest_cache", "venv", ".venv",
    "dist", "build", ".next", ".nuxt", "coverage", ".nyc_output",
    "eggs", ".eggs", "*.egg-info",
}
