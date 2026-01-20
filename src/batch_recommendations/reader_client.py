"""
Readwise Reader API client for saving articles to inbox.

API Docs: https://readwise.io/reader_api
"""

import logging
import requests
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class ReadwiseReaderClient:
    """Readwise Reader API client (v3)."""

    BASE_URL = "https://readwise.io/api/v3"

    def __init__(self, api_key: str):
        """
        Initialize Reader client.

        Args:
            api_key: Readwise API token
        """
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Token {api_key}",
                "Content-Type": "application/json",
            }
        )

    def save_url(
        self,
        url: str,
        tags: List[str],
        title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Save article to Reader inbox.

        Endpoint: POST /save/

        Args:
            url: Article URL
            tags: List of tags for organization
            title: Optional override title

        Returns:
            Saved document metadata

        Raises:
            requests.HTTPError: API error (409 for duplicate, 429 for rate limit, etc.)
        """
        payload = {"url": url, "tags": tags}
        if title:
            payload["title"] = title

        response = self.session.post(
            f"{self.BASE_URL}/save/",
            json=payload,
            timeout=10,
        )
        response.raise_for_status()

        data = response.json()
        logger.info(f"Saved {url} to Reader inbox (id: {data.get('id')})")
        return data

    def list_documents(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get all documents in Reader library (paginated).

        Endpoint: GET /list/

        Args:
            limit: Items per page (max 100)

        Returns:
            List of document objects with URL, title, tags
        """
        documents = []
        page_cursor = None

        while True:
            params = {"limit": limit}
            if page_cursor:
                params["page_cursor"] = page_cursor

            response = self.session.get(
                f"{self.BASE_URL}/list/",
                params=params,
                timeout=10,
            )
            response.raise_for_status()

            data = response.json()
            documents.extend(data.get("results", []))

            # Check for next page
            page_cursor = data.get("meta", {}).get("page_cursor")
            if not page_cursor:
                break

        logger.info(f"Fetched {len(documents)} documents from Reader library")
        return documents
