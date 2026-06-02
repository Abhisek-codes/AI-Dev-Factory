from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


class Settings:
	"""Centralized runtime configuration loaded from environment variables."""

	def __init__(self) -> None:
		project_root = Path(__file__).resolve().parents[2]
		load_dotenv(project_root / ".env")

		self.AZURE_OPENAI_ENDPOINT: str = self._parse_str(os.getenv("AZURE_OPENAI_ENDPOINT"), default="")
		self.AZURE_OPENAI_DEPLOYMENT_NAME: str = self._parse_str(
			os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
			default="",
		)

		self.FRONTEND_URL: str = self._parse_str(os.getenv("FRONTEND_URL"), default="http://localhost:8080")
		self.PORT: int = self._parse_int(os.getenv("PORT"), default=8000)
		self.DEBUG: bool = self._parse_bool(os.getenv("DEBUG"), default=False)

		self.AZURE_SUBSCRIPTION_ID: str = self._parse_str(os.getenv("AZURE_SUBSCRIPTION_ID"), default="")
		self.AZURE_RESOURCE_GROUP: str = self._parse_str(os.getenv("AZURE_RESOURCE_GROUP"), default="")

		self.AZURE_STORAGE_ACCOUNT_URL: str = self._parse_str(os.getenv("AZURE_STORAGE_ACCOUNT_URL"), default="")
		self.AZURE_STORAGE_CONTAINER_NAME: str = self._parse_str(
			os.getenv("AZURE_STORAGE_CONTAINER_NAME"), default="aetherdev-artifacts"
		)

	@staticmethod
	def _parse_str(value: str | None, *, default: str) -> str:
		if value is None:
			return default
		trimmed = value.strip()
		return trimmed if trimmed else default

	@staticmethod
	def _parse_bool(value: str | None, *, default: bool) -> bool:
		if value is None:
			return default
		normalized = value.strip().lower()
		if normalized in {"1", "true", "yes", "y", "on"}:
			return True
		if normalized in {"0", "false", "no", "n", "off"}:
			return False
		return default

	@staticmethod
	def _parse_int(value: str | None, *, default: int) -> int:
		if value is None:
			return default
		try:
			return int(value.strip())
		except (TypeError, ValueError):
			return default


settings = Settings()
