import keyring
import keyring.errors
from typing import Optional

# Service name to use for storing the token in the OS keyring
SERVICE_NAME = "vimeo-backup-tool"
# We store the token against a generic username within the service
KEYRING_USERNAME = "vimeo_pat"


def store_token(token: str) -> bool:
    """Stores the Vimeo Personal Access Token securely in the OS keyring.

    Args:
        token: The Vimeo PAT string.

    Returns:
        True if storage was successful, False otherwise.
    """
    try:
        keyring.set_password(SERVICE_NAME, KEYRING_USERNAME, token)
        return True
    except keyring.errors.PasswordSetError as e:
        # Consider logging the error e
        return False


def get_token() -> Optional[str]:
    """Retrieves the Vimeo Personal Access Token from the OS keyring.

    Returns:
        The stored token string, or None if not found or an error occurred.
    """
    try:
        return keyring.get_password(SERVICE_NAME, KEYRING_USERNAME)
    except keyring.errors.KeyringError as e:
        # Consider logging the error e
        return None 