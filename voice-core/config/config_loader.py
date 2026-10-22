# config/config_loader.py
import os
from typing import Dict, Any, Optional
import yaml
from dotenv import load_dotenv
from pathlib import Path

class Config:
    def __init__(self, config_path: Optional[str] = None):
        load_dotenv(".env")

        # Get the directory where this config_loader.py file is located
        config_dir = Path(__file__).parent

        # Set the config path - look in the same directory as this file
        if config_path is None:
            self.config_path = config_dir / "config.yaml"
        else:
            self.config_path = Path(config_path)

        print(f"🔍 Looking for config file at: {self.config_path}")
        self._config = self._load_config()
        print("✅ Config loaded successfully!")

    def _load_config(self) -> Dict[str, Any]:
        """Load and parse the YAML configuration file"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, 'r') as file:
            config = yaml.safe_load(file)

        # Replace environment variable placeholders
        return self._resolve_env_vars(config)

    def _resolve_env_vars(self, config: Dict) -> Dict:
        """Recursively resolve environment variable placeholders in config"""
        if isinstance(config, dict):
            return {k: self._resolve_env_vars(v) for k, v in config.items()}
        elif isinstance(config, list):
            return [self._resolve_env_vars(item) for item in config]
        elif isinstance(config, str) and config.startswith("${") and config.endswith("}"):
            env_var = config[2:-1]
            env_value = os.getenv(env_var)
            if env_value is None:
                print(f"⚠️  Environment variable {env_var} not found, using placeholder")
                return config
            return env_value
        else:
            return config

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation"""
        keys = key.split('.')
        value = self._config

        try:
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            return value
        except (AttributeError, TypeError):
            return default

    def validate_required_keys(self, required_keys: list) -> None:
        """Validate that required configuration keys are present"""
        missing_keys = []
        for key in required_keys:
            if self.get(key) is None:
                missing_keys.append(key)

        if missing_keys:
            raise ValueError(f"Missing required configuration keys: {missing_keys}")

# Global config instance
config = Config()