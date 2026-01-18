"""
Date extraction from web pages.

Extracts publication dates from HTML when Tavily doesn't provide them.
Uses parallel fetching for performance.
"""

import logging
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
from datetime import datetime

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_TIMEOUT = 3.0  # seconds per request
MAX_WORKERS = 10  # parallel requests
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def extract_date_from_html(html: str) -> Optional[str]:
    """
    Extract publication date from HTML content.

    Tries multiple sources in order of reliability:
    1. JSON-LD Schema.org (most reliable)
    2. Meta tags (Open Graph, article:published_time, etc.)
    3. <time> elements with datetime attribute

    Args:
        html: Raw HTML content

    Returns:
        Date string if found, None otherwise
    """
    try:
        soup = BeautifulSoup(html, "html.parser")

        # 1. JSON-LD Schema.org (most reliable)
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                if not script.string:
                    continue
                data = json.loads(script.string)
                date = _extract_date_from_jsonld(data)
                if date:
                    return date
            except (json.JSONDecodeError, TypeError):
                continue

        # 2. Meta tags
        meta_selectors = [
            ("property", "article:published_time"),
            ("property", "og:article:published_time"),
            ("name", "pubdate"),
            ("name", "publishdate"),
            ("name", "date"),
            ("name", "DC.date.issued"),
            ("itemprop", "datePublished"),
        ]
        for attr, value in meta_selectors:
            tag = soup.find("meta", {attr: value})
            if tag and tag.get("content"):
                return tag["content"]

        # 3. <time> element with datetime attribute
        time_tag = soup.find("time", datetime=True)
        if time_tag and time_tag.get("datetime"):
            return time_tag["datetime"]

        return None

    except Exception as e:
        logger.debug(f"Error parsing HTML for date: {e}")
        return None


def _extract_date_from_jsonld(data) -> Optional[str]:
    """
    Extract date from JSON-LD structured data.

    Handles both single objects and arrays, including @graph structures.
    """
    date_keys = ["datePublished", "dateCreated", "publishedDate", "dateModified"]

    if isinstance(data, list):
        for item in data:
            result = _extract_date_from_jsonld(item)
            if result:
                return result
        return None

    if isinstance(data, dict):
        # Check direct properties
        for key in date_keys:
            if key in data and data[key]:
                return data[key]

        # Check @graph array
        if "@graph" in data:
            for graph_item in data["@graph"]:
                if isinstance(graph_item, dict):
                    for key in date_keys:
                        if key in graph_item and graph_item[key]:
                            return graph_item[key]

    return None


def fetch_and_extract_date(url: str, timeout: float = DEFAULT_TIMEOUT) -> Optional[str]:
    """
    Fetch a URL and extract the publication date.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds

    Returns:
        Date string if found, None otherwise
    """
    try:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        response = requests.get(
            url, headers=headers, timeout=timeout, allow_redirects=True
        )
        response.raise_for_status()

        date = extract_date_from_html(response.text)
        if date:
            logger.debug(f"Extracted date from {url}: {date}")
        return date

    except requests.exceptions.Timeout:
        logger.debug(f"Timeout fetching {url}")
        return None
    except requests.exceptions.RequestException as e:
        logger.debug(f"Error fetching {url}: {e}")
        return None
    except Exception as e:
        logger.debug(f"Unexpected error for {url}: {e}")
        return None


def extract_dates_batch(
    urls: list[str],
    timeout: float = DEFAULT_TIMEOUT,
    max_workers: int = MAX_WORKERS,
) -> dict[str, str]:
    """
    Extract publication dates from multiple URLs in parallel.

    Args:
        urls: List of URLs to process
        timeout: Timeout per request in seconds
        max_workers: Maximum parallel requests

    Returns:
        Dictionary mapping URL to extracted date string.
        Only includes URLs where date was successfully extracted.
    """
    if not urls:
        return {}

    results = {}

    logger.info(f"Extracting dates from {len(urls)} URLs (parallel, timeout={timeout}s)")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(fetch_and_extract_date, url, timeout): url
            for url in urls
        }

        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                date = future.result()
                if date:
                    results[url] = date
            except Exception as e:
                logger.debug(f"Exception for {url}: {e}")

    success_rate = len(results) / len(urls) * 100 if urls else 0
    logger.info(
        f"Date extraction complete: {len(results)}/{len(urls)} "
        f"({success_rate:.0f}% success)"
    )

    return results
