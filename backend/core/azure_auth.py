import logging
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from agent_framework_openai import OpenAIChatCompletionClient
from core.config import settings

logger = logging.getLogger(__name__)

def get_ai_client() -> OpenAIChatCompletionClient:
    """
    Initializes and returns the MAF ChatClient using Azure Managed Identity.
    """
    try:
        if not settings.AZURE_OPENAI_ENDPOINT:
            raise RuntimeError("AZURE_OPENAI_ENDPOINT is not configured.")
        if not settings.AZURE_OPENAI_DEPLOYMENT_NAME:
            raise RuntimeError("AZURE_OPENAI_DEPLOYMENT_NAME is not configured.")

        # 1. Initialize the Keyless Credential
        credential = DefaultAzureCredential()

        # 2. Scope the token provider to Azure Cognitive Services
        token_provider = get_bearer_token_provider(
            credential, 
            "https://cognitiveservices.azure.com/.default"
        )

        # 3. Instantiate a config-driven Azure OpenAI chat client.
        client = OpenAIChatCompletionClient(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT.rstrip("/"),
            model=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
            api_version="2025-01-01-preview",
            credential=token_provider,
        )
        return client
        
    except Exception as exc:
        logger.error(f"Failed to initialize Azure AI Client: {exc}", exc_info=True)
        raise RuntimeError("Authentication failed. Ensure you are logged in via Azure CLI.")