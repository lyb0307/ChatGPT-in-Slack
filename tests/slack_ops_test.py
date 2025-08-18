import unittest
from app.slack_ops import split_long_message


class TestSplitLongMessage(unittest.TestCase):
    def test_short_message(self):
        """Test that short messages are not split"""
        text = "This is a short message"
        result = split_long_message(text, max_length=100)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], text)

    def test_long_message_split(self):
        """Test that long messages are split properly"""
        text = "a" * 150  # 150 characters
        result = split_long_message(text, max_length=100)
        self.assertEqual(len(result), 2)
        # First chunk should have continuation marker
        self.assertTrue(result[0].endswith("..."))
        # Second chunk should start with continuation marker
        self.assertTrue(result[1].startswith("..."))

    def test_split_at_line_boundaries(self):
        """Test that messages are split at line boundaries when possible"""
        lines = ["Line " + str(i) * 20 for i in range(10)]
        text = "\n".join(lines)
        result = split_long_message(text, max_length=100)
        # Should have multiple chunks
        self.assertGreater(len(result), 1)
        # Each chunk should be under the limit
        for chunk in result:
            self.assertLessEqual(len(chunk), 110)  # Allow for continuation markers

    def test_code_block_preservation(self):
        """Test that code blocks are preserved across splits"""
        text = (
            "Some text\n```python\ndef long_function():\n    "
            + "x = 1\n    " * 50
            + "\n```\nMore text"
        )
        result = split_long_message(text, max_length=200)

        # Should have multiple chunks due to long code
        self.assertGreater(len(result), 1)

        # Check that code blocks are properly closed and reopened
        for i, chunk in enumerate(result):
            # Count ``` occurrences - should be even (properly paired)
            code_blocks = chunk.count("```")
            self.assertEqual(code_blocks % 2, 0, f"Chunk {i} has unpaired code blocks")

    def test_no_word_breaking(self):
        """Test that words are not broken in the middle"""
        text = (
            "This is a sentence with some relatively long words like "
            "supercalifragilisticexpialidocious and more words"
        )
        result = split_long_message(text, max_length=50)

        # Reconstruct the text from chunks (removing continuation markers)
        reconstructed = ""
        for chunk in result:
            clean_chunk = chunk.replace("...", "").strip()
            if reconstructed and not reconstructed.endswith(" "):
                reconstructed += " "
            reconstructed += clean_chunk

        # The reconstructed text should contain all the original words
        original_words = set(text.split())
        reconstructed_words = set(reconstructed.split())
        # All original words should be present and intact
        for word in original_words:
            self.assertIn(word, reconstructed_words)

    def test_empty_message(self):
        """Test handling of empty messages"""
        text = ""
        result = split_long_message(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], "")

    def test_whitespace_only_message(self):
        """Test handling of whitespace-only messages"""
        text = "   \n\n   "
        result = split_long_message(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], text)

    def test_chinese_text_byte_length(self):
        """Test that Chinese text is split based on byte length, not character count"""
        # Chinese characters typically take 3 bytes each in UTF-8
        # 100 Chinese characters = ~300 bytes
        chinese_text = "你好世界" * 100  # 400 characters, ~1200 bytes

        # With max_length of 500 bytes, this should split into multiple chunks
        result = split_long_message(chinese_text, max_length=500)

        # Should have multiple chunks
        self.assertGreater(len(result), 1)

        # Each chunk should be under 500 bytes
        for chunk in result:
            self.assertLessEqual(len(chunk.encode("utf-8")), 500)

    def test_mixed_chinese_english_text(self):
        """Test handling of mixed Chinese and English text"""
        # Mix of ASCII (1 byte) and Chinese (3 bytes) characters
        mixed_text = "Hello 你好 " * 50  # Mix of English and Chinese

        result = split_long_message(mixed_text, max_length=300)

        # Should split into multiple chunks
        self.assertGreater(len(result), 1)

        # Each chunk should be under 300 bytes + some overhead for continuation markers
        for chunk in result:
            # Allow for "..." markers which add a few extra bytes
            self.assertLessEqual(len(chunk.encode("utf-8")), 310)


if __name__ == "__main__":
    unittest.main()
