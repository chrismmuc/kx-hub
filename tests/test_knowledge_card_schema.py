"""
Unit tests for Knowledge Card Schema

Tests schema validation, constraints, and Firestore integration.
Story 2.1: Knowledge Card Generation (Epic 2)
"""

import unittest
from datetime import datetime

from src.knowledge_cards.schema import (
    FIRESTORE_SCHEMA_DOC,
    KnowledgeCard,
    validate_knowledge_card_response,
)


class TestKnowledgeCardSchema(unittest.TestCase):
    """Test KnowledgeCard schema and validation"""

    def setUp(self):
        """Set up valid test data"""
        self.valid_card_data = {
            "summary": "AI safety requires alignment between human values and model objectives.",
            "takeaways": [
                "Implement value alignment frameworks early in development",
                "Test models for unintended consequences before deployment",
                "Design interpretability tools to understand model decisions",
            ],
            "tags": ["AI safety", "alignment", "ethics"],
        }

    def test_create_valid_knowledge_card(self):
        """Test creating valid knowledge card (AC #2, #3, #6)"""
        card = KnowledgeCard(**self.valid_card_data)

        self.assertEqual(card.summary, self.valid_card_data["summary"])
        self.assertEqual(card.takeaways, self.valid_card_data["takeaways"])
        self.assertEqual(card.tags, self.valid_card_data["tags"])
        self.assertIsNotNone(card.generated_at)  # Auto-set
        self.assertTrue(card.generated_at.endswith("Z"))  # ISO format

    def test_summary_length_constraint(self):
        """Test summary ≤400 chars constraint (AC #2) - relaxed from 200 to 400"""
        # Valid: exactly 400 chars (max allowed)
        valid_summary = "A" * 400
        card = KnowledgeCard(
            summary=valid_summary,
            takeaways=["Takeaway 1", "Takeaway 2", "Takeaway 3"],
            tags=["tag1", "tag2"],
        )
        self.assertEqual(len(card.summary), 400)

        # Invalid: 401 chars
        invalid_summary = "A" * 401
        with self.assertRaises(ValueError) as ctx:
            KnowledgeCard(
                summary=invalid_summary,
                takeaways=["Takeaway 1", "Takeaway 2", "Takeaway 3"],
                tags=["tag1", "tag2"],
            )
        self.assertIn("400 character limit", str(ctx.exception))

    def test_takeaways_count_constraint(self):
        """Test takeaways must be 3-5 items (AC #3)"""
        # Valid: 3 takeaways (minimum)
        card_3 = KnowledgeCard(
            summary="Summary", takeaways=["One", "Two", "Three"], tags=["tag1"]
        )
        self.assertEqual(len(card_3.takeaways), 3)

        # Valid: 5 takeaways (maximum)
        card_5 = KnowledgeCard(
            summary="Summary",
            takeaways=["One", "Two", "Three", "Four", "Five"],
            tags=["tag1"],
        )
        self.assertEqual(len(card_5.takeaways), 5)

        # Invalid: 2 takeaways (too few)
        with self.assertRaises(ValueError) as ctx:
            KnowledgeCard(summary="Summary", takeaways=["One", "Two"], tags=["tag1"])
        self.assertIn("3-5 items", str(ctx.exception))

        # Invalid: 6 takeaways (too many)
        with self.assertRaises(ValueError) as ctx:
            KnowledgeCard(
                summary="Summary",
                takeaways=["One", "Two", "Three", "Four", "Five", "Six"],
                tags=["tag1"],
            )
        self.assertIn("3-5 items", str(ctx.exception))

    def test_tags_required(self):
        """Test at least one tag is required"""
        with self.assertRaises(ValueError) as ctx:
            KnowledgeCard(
                summary="Summary",
                takeaways=["One", "Two", "Three"],
                tags=[],  # Empty tags
            )
        self.assertIn("At least one tag", str(ctx.exception))

    def test_to_dict(self):
        """Test converting knowledge card to dict for Firestore"""
        card = KnowledgeCard(**self.valid_card_data)
        card_dict = card.to_dict()

        self.assertIsInstance(card_dict, dict)
        self.assertEqual(card_dict["summary"], card.summary)
        self.assertEqual(card_dict["takeaways"], card.takeaways)
        self.assertEqual(card_dict["tags"], card.tags)
        self.assertIn("generated_at", card_dict)

    def test_from_dict(self):
        """Test creating knowledge card from dict (Firestore load)"""
        card_dict = {
            "summary": "Test summary",
            "takeaways": ["One", "Two", "Three"],
            "tags": ["tag1", "tag2"],
            "generated_at": "2025-11-01T12:00:00Z",
        }

        card = KnowledgeCard.from_dict(card_dict)

        self.assertEqual(card.summary, card_dict["summary"])
        self.assertEqual(card.takeaways, card_dict["takeaways"])
        self.assertEqual(card.tags, card_dict["tags"])
        self.assertEqual(card.generated_at, card_dict["generated_at"])

    def test_to_json_from_json(self):
        """Test JSON serialization/deserialization"""
        card1 = KnowledgeCard(**self.valid_card_data)

        # Serialize to JSON
        json_str = card1.to_json()
        self.assertIsInstance(json_str, str)
        self.assertIn("summary", json_str)
        self.assertIn("takeaways", json_str)

        # Deserialize from JSON
        card2 = KnowledgeCard.from_json(json_str)
        self.assertEqual(card1.summary, card2.summary)
        self.assertEqual(card1.takeaways, card2.takeaways)
        self.assertEqual(card1.tags, card2.tags)

    def test_validate_llm_response_valid(self):
        """Test validating valid LLM API response"""
        llm_response = {
            "summary": "Key insight from the chunk",
            "takeaways": [
                "First actionable takeaway",
                "Second key point",
                "Third important insight",
            ],
            "tags": ["theme1", "concept1"],
        }

        card = validate_knowledge_card_response(llm_response)

        self.assertIsInstance(card, KnowledgeCard)
        self.assertEqual(card.summary, llm_response["summary"])
        self.assertEqual(len(card.takeaways), 3)
        self.assertEqual(len(card.tags), 2)

    def test_validate_llm_response_missing_field(self):
        """Test validation fails when LLM response missing fields"""
        # Missing 'summary'
        invalid_response = {"takeaways": ["One", "Two", "Three"], "tags": ["tag1"]}

        with self.assertRaises(ValueError) as ctx:
            validate_knowledge_card_response(invalid_response)
        self.assertIn("missing required fields", str(ctx.exception))
        self.assertIn("summary", str(ctx.exception))

    def test_validate_llm_response_wrong_types(self):
        """Test validation fails when LLM response has wrong types"""
        # Summary is list instead of string
        invalid_response = {
            "summary": ["This", "is", "wrong"],
            "takeaways": ["One", "Two", "Three"],
            "tags": ["tag1"],
        }

        with self.assertRaises(ValueError) as ctx:
            validate_knowledge_card_response(invalid_response)
        self.assertIn("Summary must be string", str(ctx.exception))

    def test_validate_llm_response_constraint_violations(self):
        """Test validation enforces constraints on LLM response"""
        # Summary too long (>400 chars) - relaxed from 200 to 400
        invalid_response = {
            "summary": "A" * 401,
            "takeaways": ["One", "Two", "Three"],
            "tags": ["tag1"],
        }

        with self.assertRaises(ValueError) as ctx:
            validate_knowledge_card_response(invalid_response)
        self.assertIn("400 character limit", str(ctx.exception))

    def test_firestore_schema_doc_exists(self):
        """Test Firestore schema documentation is available"""
        self.assertIsInstance(FIRESTORE_SCHEMA_DOC, str)
        self.assertIn("kb_items", FIRESTORE_SCHEMA_DOC)
        self.assertIn("knowledge_card", FIRESTORE_SCHEMA_DOC)
        self.assertIn("merge=True", FIRESTORE_SCHEMA_DOC)

    def test_auto_generated_timestamp(self):
        """Test generated_at is auto-set with ISO 8601 format"""
        card = KnowledgeCard(**self.valid_card_data)

        # Check timestamp is ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)
        self.assertRegex(
            card.generated_at, r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z"
        )

        # Check timestamp is recent (within 5 seconds)
        generated_time = datetime.fromisoformat(
            card.generated_at.replace("Z", "+00:00")
        )
        now = datetime.utcnow()
        delta = (now - generated_time.replace(tzinfo=None)).total_seconds()
        self.assertLess(delta, 5, "Timestamp should be recent")

    def test_manual_timestamp_override(self):
        """Test manually setting generated_at timestamp"""
        manual_timestamp = "2025-10-31T10:30:00Z"
        card = KnowledgeCard(
            summary="Summary",
            takeaways=["One", "Two", "Three"],
            tags=["tag1"],
            generated_at=manual_timestamp,
        )

        self.assertEqual(card.generated_at, manual_timestamp)


if __name__ == "__main__":
    unittest.main()
