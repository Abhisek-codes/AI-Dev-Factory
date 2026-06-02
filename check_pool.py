import asyncio
import aiohttp
import logging
import os
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file if present
# Configure basic logging for the terminal
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def build_credential() -> object:
    """
    Builds a credential chain suited for local dev and cloud runtimes.
    """
    # If running in Azure with managed identity configured, keep default behavior.
    # is_managed_identity_runtime = bool(
    #     os.getenv("IDENTITY_ENDPOINT")
    #     or os.getenv("MSI_ENDPOINT")
    #     or os.getenv("WEBSITE_INSTANCE_ID")
    # )
    credential = DefaultAzureCredential()
    # Local development: avoid IMDS probing delays/noise and use explicit dev credentials.
    return credential

async def verify_session_pool_connectivity(endpoint_url: str) -> bool:
    """
    Pings the Azure Container Apps Session Pool by executing a simple Python command.
    """
    if not endpoint_url:
        logger.error("Endpoint URL is missing.")
        return False

    # Clean the endpoint URL and append the execution route
    base_url = endpoint_url.rstrip('/')
    api_url = f"{base_url}/code/execute?api-version=2024-02-02-preview"
    
    # We use a hardcoded identifier for a health check session
    session_id = "health-check-session-001"
    
    # A trivial python script to prove execution capabilities
    dummy_code = "print('Session pool is connected and executing code successfully!')"

    payload = {
        "properties": {
            "identifier": session_id,
            "codeInputType": "inline",
            "executionType": "synchronous",
            "code": dummy_code
        }
    }

    try:
        logger.info("Acquiring Entra ID token...")
        credential = build_credential()
        # The specific audience required for Dynamic Sessions
        token_obj = credential.get_token("https://dynamicsessions.io/.default")
        
        headers = {
            "Authorization": f"Bearer {token_obj.token}",
            "Content-Type": "application/json"
        }
    except Exception as e:
     import traceback
     traceback.print_exc()

    logger.info(f"Pinging session pool at: {base_url}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, headers=headers, json=payload, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    stdout = data.get("properties", {}).get("stdout", "").strip()
                    logger.info(f"SUCCESS! Container output: '{stdout}'")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"HTTP {response.status}: {error_text}")
                    return False
                    
    except asyncio.TimeoutError:
        logger.error("Connection timed out. The session pool might be warming up or blocked by network rules.")
        return False
    except Exception as e:
        logger.error(f"Unexpected network error: {e}")
        return False

if __name__ == "__main__":
    # Ensure your terminal is logged in via `az login` before running
    # You can pass your endpoint directly or set it as an environment variable
    TARGET_ENDPOINT = os.getenv(
        "AZURE_CONTAINER_APPS_DYNAMIC_SESSIONS_ENDPOINT", 
        "" # Replace with your actual endpoint
    )
    print(TARGET_ENDPOINT)
    if TARGET_ENDPOINT.endswith("/..."):
        logger.error(
            "Endpoint appears to be a placeholder. Set AZURE_CONTAINER_APPS_DYNAMIC_SESSIONS_ENDPOINT to your full Dynamic Sessions endpoint."
        )
        raise SystemExit(1)
    
    # Run the async check
    success = asyncio.run(verify_session_pool_connectivity(TARGET_ENDPOINT))
    
    if success:
        print("\n✅ Connectivity Check Passed.")
    else:
        print("\n❌ Connectivity Check Failed.")