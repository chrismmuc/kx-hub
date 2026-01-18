"""
Date extraction from web pages.

Extracts publication dates from HTML when Tavily doesn't provide them.
Uses parallel fetching for performance.

Extraction strategy (in order):
1. JSON-LD Schema.org structured data
2. Meta tags (Open Graph, article:published_time, etc.)
3. <time> elements with datetime attribute
4. Text pattern matching (e.g., "July 4, 2022", "2022-07-04")
5. Gemini Flash LLM extraction (fallback for complex cases)
"""

import logging
import json
import re
import os
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

# Month name mappings for text parsing (English and German)
MONTH_NAMES = {
    # English
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
    # German
    "januar": 1, "jän": 1,
    "februar": 2,
    "märz": 3, "maerz": 3,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "oktober": 10, "okt": 10,
    "dezember": 12, "dez": 12,
}

# Combined month patterns for regex (English + German)
_EN_MONTHS = r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
_DE_MONTHS = r"januar|jän|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|okt|november|dezember|dez"
_ALL_MONTHS = f"{_EN_MONTHS}|{_DE_MONTHS}"

# Regex patterns for date extraction from text (English and German)
DATE_PATTERNS = [
    # "July 4, 2022" or "Jul 4, 2022" or "März 15, 2024" (Month Day, Year)
    rf"\b((?:{_ALL_MONTHS})\s+\d{{1,2}},?\s+\d{{4}})\b",
    # "4 July 2022" or "4. Juli 2022" or "15 März 2024" (Day Month Year)
    rf"\b(\d{{1,2}}\.?\s+(?:{_ALL_MONTHS})\s+\d{{4}})\b",
    # "2022-07-04" or "2022/07/04" (ISO)
    r"\b(\d{4}[-/]\d{2}[-/]\d{2})\b",
    # "04.07.2022" (German/European format DD.MM.YYYY)
    r"\b(\d{2}\.\d{2}\.\d{4})\b",
    # "07/04/2022" or "07-04-2022" (US format MM/DD/YYYY)
    r"\b(\d{2}[-/]\d{2}[-/]\d{4})\b",
    # "on July 4, 2022" or "am 4. Juli 2022" - with prefix
    rf"\b(?:on|am)\s+((?:{_ALL_MONTHS}|\d{{1,2}}\.?)\s+(?:\d{{1,2}},?\s+\d{{4}}|(?:{_ALL_MONTHS})\s+\d{{4}}))\b",
]


def extract_date_from_html(html: str, use_llm_fallback: bool = False) -> Optional[str]:
    """
    Extract publication date from HTML content.

    Tries multiple sources in order of reliability:
    1. JSON-LD Schema.org (most reliable)
    2. Meta tags (Open Graph, article:published_time, etc.)
    3. <time> elements with datetime attribute
    4. Text pattern matching (e.g., "July 4, 2022")
    5. Gemini Flash LLM extraction (optional fallback)

    Args:
        html: Raw HTML content
        use_llm_fallback: Whether to use Gemini Flash as final fallback

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

        # 4. Text pattern matching
        date = _extract_date_from_text(soup)
        if date:
            return date

        # 5. Gemini Flash LLM extraction (optional fallback)
        if use_llm_fallback:
            date = _extract_date_with_gemini(soup)
            if date:
                return date

        return None

    except Exception as e:
        logger.debug(f"Error parsing HTML for date: {e}")
        return None


def _extract_date_from_text(soup: BeautifulSoup) -> Optional[str]:
    """
    Extract date from visible text using regex patterns.

    Looks in common locations: header, article metadata, bylines.
    """
    # Focus on likely date-containing elements
    search_elements = []

    # Header area
    for selector in ["header", ".post-meta", ".article-meta", ".byline",
                     ".date", ".published", ".timestamp", ".age",
                     "[class*='date']", "[class*='time']", "[class*='publish']"]:
        search_elements.extend(soup.select(selector))

    # Also check first part of body if no specific elements found
    if not search_elements:
        body = soup.find("body")
        if body:
            # Get text from first 2000 chars of body
            search_elements = [body]

    seen_dates = []
    for element in search_elements:
        text = element.get_text(separator=" ", strip=True)[:2000].lower()

        for pattern in DATE_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                normalized = _normalize_date_string(match)
                if normalized:
                    seen_dates.append(normalized)

    # Return the most recent valid date (assume it's the publication date)
    if seen_dates:
        # Sort by date, newest first
        try:
            seen_dates.sort(reverse=True)
            return seen_dates[0]
        except Exception:
            return seen_dates[0]

    return None


def _normalize_date_string(date_str: str) -> Optional[str]:
    """
    Normalize various date formats to ISO format (YYYY-MM-DD).
    """
    date_str = date_str.strip()

    # Try parsing with various formats
    formats = [
        # "July 4, 2022" or "Jul 4, 2022"
        ("%B %d, %Y", None),
        ("%B %d %Y", None),
        ("%b %d, %Y", None),
        ("%b %d %Y", None),
        # "4 July 2022"
        ("%d %B %Y", None),
        ("%d %b %Y", None),
        # ISO format
        ("%Y-%m-%d", None),
        ("%Y/%m/%d", None),
        # German format "04.07.2022" (DD.MM.YYYY)
        ("%d.%m.%Y", None),
        # US format (risky, but try)
        ("%m/%d/%Y", None),
        ("%m-%d-%Y", None),
    ]

    for fmt, _ in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Handle month name variations manually
    date_lower = date_str.lower()
    for month_name, month_num in MONTH_NAMES.items():
        if month_name in date_lower:
            # Extract day and year
            numbers = re.findall(r"\d+", date_str)
            if len(numbers) >= 2:
                # Determine which is day vs year
                nums = [int(n) for n in numbers]
                year = next((n for n in nums if n > 1900), None)
                day = next((n for n in nums if 1 <= n <= 31 and n != year), None)
                if year and day:
                    try:
                        return f"{year}-{month_num:02d}-{day:02d}"
                    except Exception:
                        pass

    return None


def _extract_date_with_gemini(soup: BeautifulSoup) -> Optional[str]:
    """
    Use Gemini Flash to extract publication date from HTML.

    This is a fallback for pages where structured data and patterns fail.
    """
    try:
        # Import here to avoid circular dependencies
        from llm import gemini_client

        # Get relevant text (title, first paragraphs, metadata areas)
        title = soup.find("title")
        title_text = title.get_text(strip=True) if title else ""

        # Get header/meta text
        meta_text = ""
        for selector in ["header", ".post-meta", ".byline", ".article-info"]:
            for el in soup.select(selector)[:2]:
                meta_text += " " + el.get_text(separator=" ", strip=True)[:500]

        # First paragraph
        first_p = soup.find("p")
        first_p_text = first_p.get_text(strip=True)[:300] if first_p else ""

        context = f"Title: {title_text}\nMetadata: {meta_text[:800]}\nFirst paragraph: {first_p_text}"

        prompt = f"""Extract the publication date from this webpage content.
Return ONLY the date in YYYY-MM-DD format, nothing else.
If no publication date is found, return "NONE".

Content:
{context}

Date:"""

        # Use Gemini Flash for speed
        client = gemini_client.GeminiClient(model="gemini-2.0-flash")
        response = client.generate(prompt, max_tokens=20, temperature=0)

        result = response.strip()
        if result and result != "NONE":
            # Validate it's a proper date
            try:
                datetime.strptime(result, "%Y-%m-%d")
                logger.debug(f"Gemini extracted date: {result}")
                return result
            except ValueError:
                pass

        return None

    except Exception as e:
        logger.debug(f"Gemini date extraction failed: {e}")
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


def fetch_and_extract_date(
    url: str,
    timeout: float = DEFAULT_TIMEOUT,
    use_llm_fallback: bool = True,
) -> Optional[str]:
    """
    Fetch a URL and extract the publication date.

    Uses structured data, meta tags, text patterns, and optionally
    Gemini Flash as a fallback for complex cases.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds
        use_llm_fallback: Whether to use Gemini Flash for hard cases

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

        date = extract_date_from_html(response.text, use_llm_fallback=use_llm_fallback)
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
