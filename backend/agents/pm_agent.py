import logging
import os

from agent_framework import Agent

from core.azure_auth import get_ai_client

logger = logging.getLogger(__name__)


def get_pm_agent() -> Agent:
	"""Initializes and returns the Product Manager Agent."""
	try:
		current_dir = os.path.dirname(os.path.abspath(__file__))
		prompt_path = os.path.join(current_dir, "prompts", "pm_agent.txt")

		with open(prompt_path, "r", encoding="utf-8") as file:
			system_instructions = file.read()

		return Agent(
			name="ProductManager",
			client=get_ai_client(),
			instructions=system_instructions,
		)
	except FileNotFoundError:
		logger.error("Prompt file not found at: %s", prompt_path)
		print(f"Error: Prompt file not found at: {prompt_path}")
		raise
