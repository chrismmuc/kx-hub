"""
Readwise Reader API client for fetching tagged documents with full content.

Story 13.1: Reader API Client
- Fetch documents tagged 'kx-auto'
- Extract full HTML content and convert to clean text
- Extract metadata (title, author, source_url, word_count, reading_time)
- Store raw responses in GCS for audit trail
- Rate limiting and retry logic

API Docs: https://readwise.io/reader_api
Rate Limits: 20 req/min (general), 50 req/min (list endpoint)
"""

import hashlib
import json
import logging
import re
import time
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
import requests
from google.cloud import storage

logger = logging.getLogger(__name__)


class ReaderDocument:
    """Represents a Reader document with extracted content and metadata."""

    def __init__(self, raw_data: Dict[str, Any], clean_text: str, word_count: int):
        """
        Initialize Reader document.

        Args:
            raw_data: Raw API response data
            clean_text: HTML converted to clean text
            word_count: Calculated word count
        """
        self.raw_data = raw_data
        self.clean_text = clean_text
        self.word_count = word_count

        # Extract metadata from raw data
        self.id = raw_data.get("id")
        self.title = raw_data.get("title", "Untitled")
        self.author = raw_data.get("author")
        self.source_url = raw_data.get("source_url") or raw_data.get("url")
        self.tags = raw_data.get("tags", [])
        self.reading_time = raw_data.get("reading_progress")  # minutes if available
        self.category = raw_data.get("category")  # article, book, pdf, etc.
        self.created_at = raw_data.get("created_at")
        self.updated_at = raw_data.get("updated_at")
        self.html_content = raw_data.get("html_content", "") or raw_data.get("html", "") or raw_data.get("content", "")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/processing."""
        return {
            "id": self.id,
            "title": self.title,
            "author": self.author,
            "source_url": self.source_url,
            "tags": self.tags,
            "reading_time": self.reading_time,
            "category": self.category,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "clean_text": self.clean_text,
            "word_count": self.word_count,
        }


class ReadwiseReaderClient:
    """Readwise Reader API v3 client for fetching documents with full content."""

    BASE_URL = "https://readwise.io/api/v3"
    # Rate limits: 20 req/min general, 50 req/min for list endpoint
    RATE_LIMIT_LIST = 50  # requests per minute
    RATE_LIMIT_GENERAL = 20  # requests per minute

    def __init__(self, api_key: str, storage_client: Optional[storage.Client] = None):
        """
        Initialize Reader client.

        Args:
            api_key: Readwise API token
            storage_client: Optional GCS client (for storing raw JSON)
        """
        self.api_key = api_key
        self.storage_client = storage_client
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Token {api_key}",
                "Content-Type": "application/json",
            }
        )

        # Track request times for rate limiting
        self._list_request_times: List[float] = []
        self._general_request_times: List[float] = []

    def _rate_limit(self, endpoint_type: str = "general") -> None:
        """
        Enforce rate limiting before making requests.

        Args:
            endpoint_type: "list" (50/min) or "general" (20/min)
        """
        limit = self.RATE_LIMIT_LIST if endpoint_type == "list" else self.RATE_LIMIT_GENERAL
        request_times = (
            self._list_request_times
            if endpoint_type == "list"
            else self._general_request_times
        )

        # Clean up requests older than 1 minute
        now = time.time()
        cutoff = now - 60
        request_times[:] = [t for t in request_times if t > cutoff]

        # If at limit, wait until oldest request expires
        if len(request_times) >= limit:
            oldest = request_times[0]
            wait_time = 60 - (now - oldest) + 0.1  # Add small buffer
            if wait_time > 0:
                logger.info(
                    f"Rate limit reached ({limit}/min). Waiting {wait_time:.1f}s..."
                )
                time.sleep(wait_time)
                # Clean up again after waiting
                now = time.time()
                cutoff = now - 60
                request_times[:] = [t for t in request_times if t > cutoff]

        # Record this request
        request_times.append(time.time())

    def _make_request(
        self,
        method: str,
        endpoint: str,
        endpoint_type: str = "general",
        max_retries: int = 3,
        timeout: int = 30,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Make API request with rate limiting and retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            endpoint_type: "list" or "general" for rate limiting
            max_retries: Maximum retry attempts
            timeout: Request timeout in seconds
            **kwargs: Additional request parameters

        Returns:
            Parsed JSON response

        Raises:
            requests.HTTPError: API error
        """
        url = f"{self.BASE_URL}{endpoint}"

        for attempt in range(max_retries):
            try:
                # Rate limit before request
                self._rate_limit(endpoint_type)

                response = self.session.request(
                    method, url, timeout=timeout, **kwargs
                )

                # Handle rate limiting (429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    logger.warning(
                        f"Rate limited. Retrying after {retry_after}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    if attempt < max_retries - 1:
                        time.sleep(retry_after)
                        continue
                    else:
                        response.raise_for_status()

                response.raise_for_status()
                return response.json()

            except requests.exceptions.Timeout:
                logger.error(f"Request timeout (attempt {attempt + 1}/{max_retries})")
                if attempt == max_retries - 1:
                    raise
                time.sleep(2**attempt)  # Exponential backoff

            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {e} (attempt {attempt + 1}/{max_retries})")
                if attempt == max_retries - 1:
                    raise
                time.sleep(2**attempt)

        raise Exception("Max retries exceeded")

    def update_document_tags(
        self,
        document_id: str,
        current_tags: List[str],
        remove_tags: Optional[List[str]] = None,
        add_tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Update tags on a Reader document.

        Endpoint: PATCH /api/v3/update/{document_id}/
        Reader API uses full tag replacement, so we compute the new set.

        Args:
            document_id: Reader document ID
            current_tags: Current tag list from ReaderDocument.tags
            remove_tags: Tags to remove
            add_tags: Tags to add

        Returns:
            Parsed JSON response from Reader API
        """
        new_tags = set(current_tags)
        for tag in (remove_tags or []):
            new_tags.discard(tag)
        for tag in (add_tags or []):
            new_tags.add(tag)

        return self._make_request(
            "PATCH",
            f"/update/{document_id}/",
            endpoint_type="general",
            json={"tags": sorted(new_tags)},
        )

    def fetch_tagged_documents(
        self,
        tag: str = "kx-auto",
        category: str = "article",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Fetch all documents with specified tag from Reader.

        Endpoint: GET /list/?tag={tag}&category={category}

        Args:
            tag: Tag to filter by (default: "kx-auto")
            category: Document category (default: "article")
            limit: Items per page (max 100)

        Returns:
            List of document objects with full content

        Note:
            - Uses list endpoint rate limit (50 req/min)
            - Handles pagination automatically
            - Returns full document objects including html_content
        """
        logger.info(f"Fetching documents with tag='{tag}', category='{category}'")
        documents = []
        page_cursor = None

        while True:
            params = {"limit": limit, "withHtmlContent": True}
            if tag:
                params["tag"] = tag
            if category:
                params["category"] = category
            if page_cursor:
                params["page_cursor"] = page_cursor

            data = self._make_request(
                "GET",
                "/list/",
                endpoint_type="list",
                params=params,
            )

            results = data.get("results", [])
            documents.extend(results)
            logger.info(f"Fetched {len(results)} documents (total: {len(documents)})")

            # Check for next page
            page_cursor = data.get("nextPageCursor")
            if not page_cursor:
                break

        logger.info(f"Completed: {len(documents)} documents fetched")
        return documents

    def html_to_clean_text(self, html: str) -> str:
        """
        Convert HTML content to clean text.

        Args:
            html: Raw HTML content from Reader API

        Returns:
            Clean text with boilerplate removed

        Process:
            - Parse HTML with BeautifulSoup
            - Remove nav, ads, scripts, styles
            - Extract main content text
            - Normalize whitespace
        """
        if not html:
            return ""

        soup = BeautifulSoup(html, "html.parser")

        # Remove unwanted elements
        for element in soup.find_all(
            ["script", "style", "nav", "header", "footer", "aside", "iframe"]
        ):
            element.decompose()

        # Extract text
        text = soup.get_text(separator=" ", strip=True)

        # Normalize whitespace
        text = re.sub(r"\s+", " ", text)
        text = text.strip()

        return text

    def calculate_word_count(self, text: str) -> int:
        """
        Calculate word count from text.

        Args:
            text: Clean text content

        Returns:
            Word count
        """
        if not text:
            return 0
        words = text.split()
        return len(words)

    def extract_document_content(self, raw_doc: Dict[str, Any]) -> ReaderDocument:
        """
        Extract content and metadata from raw Reader document.

        Args:
            raw_doc: Raw document object from Reader API

        Returns:
            ReaderDocument with extracted content and metadata
        """
        # Get HTML content (field name may vary)
        html = raw_doc.get("html_content", "") or raw_doc.get("html", "") or raw_doc.get("content", "")

        # Convert to clean text
        clean_text = self.html_to_clean_text(html)

        # Calculate word count (use API value if available, else calculate)
        word_count = raw_doc.get("word_count")
        if not word_count:
            word_count = self.calculate_word_count(clean_text)

        return ReaderDocument(raw_doc, clean_text, word_count)

    def store_raw_document(
        self,
        bucket_name: str,
        document: ReaderDocument,
    ) -> str:
        """
        Store raw Reader document JSON in GCS.

        Args:
            bucket_name: GCS bucket name
            document: ReaderDocument to store

        Returns:
            GCS URI (gs://bucket/filename)

        Raises:
            ValueError: If storage_client not configured
        """
        if not self.storage_client:
            raise ValueError("storage_client not configured")

        file_name = f"reader-doc-{document.id}.json"
        raw_json = json.dumps(document.raw_data, indent=2, sort_keys=True)

        bucket = self.storage_client.bucket(bucket_name)
        blob = bucket.blob(file_name)
        blob.upload_from_string(data=raw_json, content_type="application/json")

        uri = f"gs://{bucket_name}/{file_name}"
        logger.info(f"Stored raw document: {uri}")
        return uri

    def fetch_and_process_documents(
        self,
        tag: str = "kx-auto",
        category: str = "article",
        store_raw: bool = True,
        raw_bucket: Optional[str] = None,
    ) -> List[ReaderDocument]:
        """
        Fetch tagged documents, extract content, and optionally store raw JSON.

        Args:
            tag: Tag to filter by
            category: Document category
            store_raw: Whether to store raw JSON in GCS
            raw_bucket: GCS bucket for raw JSON (required if store_raw=True)

        Returns:
            List of processed ReaderDocument objects

        Raises:
            ValueError: If store_raw=True but raw_bucket not provided
        """
        if store_raw and not raw_bucket:
            raise ValueError("raw_bucket required when store_raw=True")

        # Fetch documents
        raw_documents = self.fetch_tagged_documents(tag=tag, category=category)
        logger.info(f"Processing {len(raw_documents)} documents")

        processed = []
        for raw_doc in raw_documents:
            # Extract content and metadata
            doc = self.extract_document_content(raw_doc)
            processed.append(doc)

            # Store raw JSON
            if store_raw:
                try:
                    self.store_raw_document(raw_bucket, doc)
                except Exception as e:
                    logger.error(f"Failed to store raw document {doc.id}: {e}")
                    # Continue processing even if storage fails

            logger.info(
                f"Processed: {doc.title[:50]}... "
                f"({doc.word_count} words, {len(doc.clean_text)} chars)"
            )

        return processed
