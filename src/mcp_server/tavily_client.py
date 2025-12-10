"""
Tavily Search API client for reading recommendations.

Story 3.5: AI-Powered Reading Recommendations

Provides web search capabilities for discovering new articles based on
knowledge base themes and clusters. Uses domain whitelisting for quality.
"""

import os
import time
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF = 1  # seconds
MAX_BACKOFF = 16  # seconds

# Global client cache
_tavily_client = None


def get_tavily_api_key() -> str:
    """
    Get Tavily API key from environment or Secret Manager.

    Returns:
        Tavily API key string

    Raises:
        ValueError: If API key is not configured
    """
    # First check environment variable (for local dev)
    api_key = os.getenv('TAVILY_API_KEY')
    if api_key:
        logger.info("Using Tavily API key from environment")
        return api_key

    # Try Secret Manager
    try:
        from google.cloud import secretmanager

        project = os.getenv('GCP_PROJECT')
        if not project:
            raise ValueError("GCP_PROJECT environment variable not set")

        client = secretmanager.SecretManagerServiceClient()
        secret_name = f"projects/{project}/secrets/tavily-api-key/versions/latest"

        logger.info(f"Fetching Tavily API key from Secret Manager: {secret_name}")
        response = client.access_secret_version(request={"name": secret_name})
        api_key = response.payload.data.decode("UTF-8")

        logger.info("Successfully retrieved Tavily API key from Secret Manager")
        return api_key

    except Exception as e:
        logger.error(f"Failed to get Tavily API key: {e}")
        raise ValueError(
            "Tavily API key not found. Set TAVILY_API_KEY env var or "
            "create 'tavily-api-key' secret in Secret Manager"
        ) from e


def get_tavily_client():
    """
    Get or create Tavily client instance (cached).

    Returns:
        Initialized TavilyClient
    """
    global _tavily_client

    if _tavily_client is None:
        from tavily import TavilyClient

        api_key = get_tavily_api_key()
        _tavily_client = TavilyClient(api_key=api_key)
        logger.info("Tavily client initialized successfully")

    return _tavily_client


def search(
    query: str,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    days: int = 30,
    max_results: int = 10,
    search_depth: str = "basic",
    topic: str = "general"
) -> Dict[str, Any]:
    """
    Search the web using Tavily API with domain filtering and recency constraints.

    Args:
        query: Search query string
        include_domains: List of domains to include (max 300)
        exclude_domains: List of domains to exclude
        days: Only return results from last N days
        max_results: Maximum number of results (default 10)
        search_depth: "basic" (fast) or "advanced" (more thorough)
        topic: "general" or "news"

    Returns:
        Dictionary with search results:
        {
            "query": str,
            "results": [
                {
                    "title": str,
                    "url": str,
                    "content": str,  # Snippet
                    "published_date": str | None,
                    "domain": str,
                    "score": float
                }
            ],
            "response_time": float,
            "result_count": int
        }

    Raises:
        Exception: If search fails after retries
    """
    client = get_tavily_client()
    backoff = INITIAL_BACKOFF

    for attempt in range(MAX_RETRIES):
        try:
            logger.info(
                f"Tavily search (attempt {attempt + 1}/{MAX_RETRIES}): "
                f"query='{query[:50]}...', domains={len(include_domains or [])}, days={days}"
            )

            start_time = time.time()

            # Build search parameters
            search_params = {
                "query": query,
                "max_results": max_results,
                "search_depth": search_depth,
                "topic": topic,
            }

            # Add domain filtering
            if include_domains:
                # Tavily allows up to 300 domains
                search_params["include_domains"] = include_domains[:300]

            if exclude_domains:
                search_params["exclude_domains"] = exclude_domains

            # Add recency filter (Tavily uses days parameter)
            if days and days > 0:
                search_params["days"] = days

            # Execute search
            response = client.search(**search_params)

            response_time = time.time() - start_time

            # Parse and format results
            results = []
            for item in response.get("results", []):
                # Extract domain from URL
                url = item.get("url", "")
                domain = _extract_domain(url)

                results.append({
                    "title": item.get("title", ""),
                    "url": url,
                    "content": item.get("content", ""),  # Snippet
                    "published_date": item.get("published_date"),
                    "domain": domain,
                    "score": item.get("score", 0.0)
                })

            logger.info(f"Tavily search completed: {len(results)} results in {response_time:.2f}s")

            return {
                "query": query,
                "results": results,
                "response_time": round(response_time, 2),
                "result_count": len(results)
            }

        except Exception as e:
            error_str = str(e).lower()

            # Check for rate limit errors
            if "rate" in error_str or "limit" in error_str or "429" in error_str:
                if attempt < MAX_RETRIES - 1:
                    logger.warning(
                        f"Tavily rate limit (attempt {attempt + 1}/{MAX_RETRIES}), "
                        f"retrying after {backoff}s"
                    )
                    time.sleep(backoff)
                    backoff = min(backoff * 2, MAX_BACKOFF)
                    continue

            # Check for server errors (5xx)
            if "500" in error_str or "502" in error_str or "503" in error_str:
                if attempt < MAX_RETRIES - 1:
                    logger.warning(
                        f"Tavily server error (attempt {attempt + 1}/{MAX_RETRIES}), "
                        f"retrying after {backoff}s"
                    )
                    time.sleep(backoff)
                    backoff = min(backoff * 2, MAX_BACKOFF)
                    continue

            # For other errors, fail immediately
            logger.error(f"Tavily search failed: {e}")
            raise Exception(f"Tavily search failed: {e}") from e

    # Should never reach here
    raise Exception("Tavily search failed after maximum retries")


def _extract_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Remove www. prefix
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def search_batch(
    queries: List[str],
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    days: int = 30,
    max_results_per_query: int = 5
) -> List[Dict[str, Any]]:
    """
    Execute multiple searches and aggregate results.

    Args:
        queries: List of search queries
        include_domains: List of domains to include
        exclude_domains: List of domains to exclude
        days: Only return results from last N days
        max_results_per_query: Max results per query (default 5)

    Returns:
        List of search result dictionaries (one per query)
    """
    logger.info(f"Executing batch search: {len(queries)} queries")

    results = []
    for query in queries:
        try:
            result = search(
                query=query,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
                days=days,
                max_results=max_results_per_query
            )
            results.append(result)
        except Exception as e:
            logger.error(f"Batch search failed for query '{query[:50]}...': {e}")
            # Continue with other queries
            results.append({
                "query": query,
                "results": [],
                "error": str(e),
                "result_count": 0
            })

    total_results = sum(r.get("result_count", 0) for r in results)
    logger.info(f"Batch search completed: {total_results} total results from {len(queries)} queries")

    return results
