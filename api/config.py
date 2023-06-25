# -*- coding: utf-8 -*-
import os
from typing import Optional

from dotenv import load_dotenv


class Settings:
    """Class to hold all environment settings."""

    _instance = None
    default_env_file = ".env"  # Set the default env_file path here


    def __new__(cls, env_file: Optional[str] = None, env: Optional[dict] = None):
        if cls._instance is None:
            cls._instance = super(Settings, cls).__new__(cls)
            cls._instance.__initiated = False
        return cls._instance

    def __init__(self, env_file: Optional[str] = None, env: Optional[dict] = None):
        if self.__initiated:
            return
        self.__initiated = True
        if env is None:
            self.env = os.environ
            if env_file is None:
                env_file = self.default_env_file  # Set the default env_file path if not provided
            load_dotenv(dotenv_path=env_file, verbose=True)
        else:
            self.env = env

        self.ENVIRONMENT = self.get_env_variable("ENVIRONMENT", "dev")
        self.HOST = self.get_env_variable("HOST", "0.0.0.0")
        self.PORT = int(self.get_env_variable("PORT", 8000))
        self.RELOAD = bool(self.get_env_variable("RELOAD", True))

        self.SECRET_KEY = self.get_env_variable(
            "SECRET_KEY",
            "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7",
        )
        self.ALGORITHM = self.get_env_variable("ALGORITHM", "HS256")
        self.ACCESS_TOKEN_EXPIRE_MINUTES = int(
            self.get_env_variable("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24 * 7)
        )

    def get_env_variable(
        self, var_name: str, default: Optional[str] = None
    ) -> Optional[str]:
        """Get environment variable value or return None if not found."""
        if var_value := self.env.get(var_name):
            return var_value
        if default is not None:
            return default
        print(f"Warning: {var_name} environment variable not set.")
        return None

    @classmethod
    def reset(cls):
        cls._instance = None