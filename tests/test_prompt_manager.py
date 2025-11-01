"""
Unit tests for Prompt Manager

Tests prompt loading, formatting, and cost estimation.
Story 2.1: Knowledge Card Generation (Epic 2)
"""

import unittest
import tempfile
import os
from pathlib import Path
from src.knowledge_cards.prompt_manager import (
    PromptManager,
    create_knowledge_card_prompt,
    estimate_cost,
    ESTIMATED_INPUT_TOKENS_PER_CHUNK,
    ESTIMATED_OUTPUT_TOKENS_PER_CHUNK
)


class TestPromptManager(unittest.TestCase):
    """Test PromptManager functionality"""

    def setUp(self):
        """Set up test prompt manager"""
        self.pm = PromptManager()

    def test_load_default_prompt(self):
        """Test loading default knowledge card prompt"""
        prompt = self.pm.load_prompt()

        self.assertIsInstance(prompt, str)
        self.assertIn('knowledge management', prompt.lower())
        self.assertIn('summary', prompt.lower())
        self.assertIn('takeaways', prompt.lower())
        self.assertIn('tags', prompt.lower())
        self.assertIn('{title}', prompt)
        self.assertIn('{author}', prompt)
        self.assertIn('{content}', prompt)

    def test_load_prompt_caching(self):
        """Test prompt is cached after first load"""
        prompt1 = self.pm.load_prompt()
        prompt2 = self.pm.load_prompt()

        self.assertIs(prompt1, prompt2)  # Same object (cached)

    def test_load_nonexistent_prompt(self):
        """Test loading nonexistent prompt raises FileNotFoundError"""
        with self.assertRaises(FileNotFoundError) as ctx:
            self.pm.load_prompt('nonexistent_prompt.txt')

        self.assertIn('not found', str(ctx.exception))

    def test_format_prompt(self):
        """Test formatting prompt with chunk data (AC #2, #3)"""
        title = "Deep Work"
        author = "Cal Newport"
        content = "The ability to perform deep work is becoming rare..."

        formatted = self.pm.format_prompt(title, author, content)

        self.assertIsInstance(formatted, str)
        self.assertIn(title, formatted)
        self.assertIn(author, formatted)
        self.assertIn(content, formatted)
        self.assertNotIn('{title}', formatted)  # Placeholders replaced
        self.assertNotIn('{author}', formatted)
        self.assertNotIn('{content}', formatted)

    def test_format_prompt_with_special_chars(self):
        """Test formatting prompt handles special characters"""
        title = "AI & ML: A Guide"
        author = "O'Reilly"
        content = 'He said: "This is important" (emphasis added)'

        formatted = self.pm.format_prompt(title, author, content)

        self.assertIn(title, formatted)
        self.assertIn(author, formatted)
        self.assertIn(content, formatted)

    def test_get_prompt_stats(self):
        """Test getting prompt statistics for cost estimation"""
        # Create sample prompt
        prompt = "This is a test prompt with some content."

        stats = self.pm.get_prompt_stats(prompt)

        self.assertIn('char_count', stats)
        self.assertIn('word_count', stats)
        self.assertIn('estimated_tokens', stats)

        self.assertEqual(stats['char_count'], len(prompt))
        self.assertEqual(stats['word_count'], len(prompt.split()))
        self.assertEqual(stats['estimated_tokens'], len(prompt) // 4)

    def test_create_knowledge_card_prompt_convenience(self):
        """Test convenience function for creating prompts"""
        prompt = create_knowledge_card_prompt(
            title="Test Title",
            author="Test Author",
            content="Test content here"
        )

        self.assertIsInstance(prompt, str)
        self.assertIn("Test Title", prompt)
        self.assertIn("Test Author", prompt)
        self.assertIn("Test content here", prompt)


class TestCostEstimation(unittest.TestCase):
    """Test cost estimation functions (AC #4)"""

    def test_estimate_cost_single_chunk(self):
        """Test cost estimation for single chunk"""
        cost = estimate_cost(1)

        self.assertIn('input_cost', cost)
        self.assertIn('output_cost', cost)
        self.assertIn('total_cost', cost)
        self.assertIn('cost_per_chunk', cost)

        # Verify calculation
        expected_input = (ESTIMATED_INPUT_TOKENS_PER_CHUNK / 1_000_000) * 0.10
        expected_output = (ESTIMATED_OUTPUT_TOKENS_PER_CHUNK / 1_000_000) * 0.40

        self.assertAlmostEqual(cost['input_cost'], expected_input, places=5)
        self.assertAlmostEqual(cost['output_cost'], expected_output, places=5)
        self.assertAlmostEqual(cost['total_cost'], expected_input + expected_output, places=5)

    def test_estimate_cost_full_corpus(self):
        """Test cost estimation for 813 chunks (AC #4)"""
        cost = estimate_cost(813)

        # From story dev notes: estimated ~$0.09/month
        self.assertLessEqual(cost['total_cost'], 0.10, "Cost must be ≤$0.10/month")
        self.assertGreater(cost['total_cost'], 0.0)

        # Verify breakdown makes sense
        self.assertGreater(cost['output_cost'], cost['input_cost'],
                          "Output tokens cost more per token than input")

    def test_estimate_cost_zero_chunks(self):
        """Test cost estimation handles zero chunks"""
        cost = estimate_cost(0)

        self.assertEqual(cost['input_cost'], 0.0)
        self.assertEqual(cost['output_cost'], 0.0)
        self.assertEqual(cost['total_cost'], 0.0)
        self.assertEqual(cost['cost_per_chunk'], 0.0)

    def test_estimate_cost_scaling(self):
        """Test cost scales linearly with chunks"""
        cost_100 = estimate_cost(100)
        cost_200 = estimate_cost(200)

        # Cost should roughly double
        self.assertAlmostEqual(
            cost_200['total_cost'],
            cost_100['total_cost'] * 2,
            places=3
        )


class TestPromptCustomization(unittest.TestCase):
    """Test custom prompt templates"""

    def test_format_custom_prompt(self):
        """Test formatting with custom prompt template"""
        custom_prompt = "Title: {title}\nAuthor: {author}\nContent: {content}"

        pm = PromptManager()
        formatted = pm.format_prompt(
            title="My Title",
            author="My Author",
            content="My content",
            prompt_template=custom_prompt
        )

        self.assertEqual(
            formatted,
            "Title: My Title\nAuthor: My Author\nContent: My content"
        )

    def test_custom_prompt_directory(self):
        """Test using custom prompt directory"""
        # Create temporary directory with custom prompt
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_prompt_path = Path(tmpdir) / 'test_prompt.txt'
            custom_prompt_path.write_text('Custom prompt: {title}')

            pm = PromptManager(prompt_dir=tmpdir)
            prompt = pm.load_prompt('test_prompt.txt')

            self.assertEqual(prompt, 'Custom prompt: {title}')


if __name__ == '__main__':
    unittest.main()
