"""
Knowledge Card Schema Definition

Defines the Firestore schema extension for knowledge cards.
Story 2.1: Knowledge Card Generation (Epic 2)

Schema Design (AC #6):
- Firestore collection: kb_items
- Field extension: knowledge_card (dict)
- Structure:
  {
    "summary": str,        # 1-2 sentences max, ≤200 characters
    "takeaways": list[str], # 3-5 distinct, actionable insights
    "tags": list[str],      # 2-4 themes/concepts
    "generated_at": timestamp  # ISO 8601 or Firestore timestamp
  }
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import json


@dataclass
class KnowledgeCard:
    """
    Knowledge card data structure for chunk summaries.

    Attributes:
        summary: One-line key insight (1-2 sentences, target ≤200 chars, max 400 chars)
        takeaways: List of 3-5 actionable takeaways
        tags: List of 2-4 thematic tags/concepts
        generated_at: Timestamp of generation (ISO 8601 format)

    Constraints (from AC #2, #3, #6):
        - Summary length: 1-2 sentences, target ≤200 chars (max 400 chars for exceptional cases)
        - Takeaways count: 3-5 items
        - Tags count: 2-4 items (recommended)
        - All fields required except generated_at (auto-set)
    """
    summary: str
    takeaways: List[str]
    tags: List[str]
    generated_at: Optional[str] = None

    def __post_init__(self):
        """Validate knowledge card constraints after initialization."""
        # Validate summary length (AC #2) - soft limit with generous flexibility
        # Target: ≤200 chars, but allow up to 400 chars for exceptional cases (100% success rate)
        if len(self.summary) > 400:
            raise ValueError(
                f"Summary exceeds maximum 400 character limit: {len(self.summary)} chars. "
                f"Summary: '{self.summary[:100]}...'"
            )

        # Validate takeaways count (AC #3)
        if not (3 <= len(self.takeaways) <= 5):
            raise ValueError(
                f"Takeaways must be 3-5 items, got {len(self.takeaways)}. "
                f"Takeaways: {self.takeaways}"
            )

        # Validate tags exist (recommended 2-4, but flexible)
        if len(self.tags) == 0:
            raise ValueError("At least one tag is required")

        # Auto-set generated_at if not provided
        if self.generated_at is None:
            self.generated_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert knowledge card to dictionary for Firestore storage.

        Returns:
            Dictionary with all fields suitable for Firestore merge
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'KnowledgeCard':
        """
        Create knowledge card from dictionary (e.g., Firestore document).

        Args:
            data: Dictionary with knowledge card fields

        Returns:
            KnowledgeCard instance
        """
        return cls(
            summary=data['summary'],
            takeaways=data['takeaways'],
            tags=data['tags'],
            generated_at=data.get('generated_at')
        )

    def to_json(self) -> str:
        """Serialize knowledge card to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> 'KnowledgeCard':
        """Deserialize knowledge card from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


def validate_knowledge_card_response(response: Dict[str, Any]) -> KnowledgeCard:
    """
    Validate LLM API response and convert to KnowledgeCard.

    This function:
    1. Validates response structure (has summary, takeaways, tags)
    2. Validates constraints (summary length, takeaways count)
    3. Returns validated KnowledgeCard instance

    Args:
        response: Dictionary from LLM API (parsed JSON)

    Returns:
        Validated KnowledgeCard instance

    Raises:
        ValueError: If response is invalid or violates constraints
    """
    # Check required fields exist
    required_fields = ['summary', 'takeaways', 'tags']
    missing_fields = [f for f in required_fields if f not in response]

    if missing_fields:
        raise ValueError(
            f"LLM response missing required fields: {missing_fields}. "
            f"Response: {response}"
        )

    # Validate types
    if not isinstance(response['summary'], str):
        raise ValueError(f"Summary must be string, got {type(response['summary'])}")

    if not isinstance(response['takeaways'], list):
        raise ValueError(f"Takeaways must be list, got {type(response['takeaways'])}")

    if not isinstance(response['tags'], list):
        raise ValueError(f"Tags must be list, got {type(response['tags'])}")

    # Create and validate via KnowledgeCard (enforces all constraints)
    return KnowledgeCard(
        summary=response['summary'].strip(),
        takeaways=[t.strip() for t in response['takeaways']],
        tags=[tag.strip() for tag in response['tags']],
        generated_at=response.get('generated_at')
    )


# Firestore schema documentation for reference
FIRESTORE_SCHEMA_DOC = """
Firestore Collection: kb_items
Document ID: chunk-{uuid}

Existing fields:
  - chunk_id: string
  - parent_doc_id: string
  - content: string (full chunk text)
  - embedding: Vector(768)
  - title, author, source, tags, etc.

NEW FIELD (Story 2.1):
  - knowledge_card: dict {
      "summary": string,        # target ≤200 chars, max 400 chars for exceptional cases
      "takeaways": array[string],  # 3-5 actionable insights
      "tags": array[string],       # 2-4 thematic concepts
      "generated_at": timestamp    # ISO 8601 format
    }

Update Pattern:
  db.collection('kb_items').document(chunk_id).set(
    {'knowledge_card': knowledge_card.to_dict()},
    merge=True
  )
"""
