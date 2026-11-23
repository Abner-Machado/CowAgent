# encoding: utf-8
"""
Tests for the two guards that keep blank text out of the embeddings API.

An OpenAI-compatible /embeddings endpoint answers 400 ("'$.input' is invalid")
when any element of the input array is an empty string, which fails the whole
batch and, in memory sync, aborts the entire index build. Blank text therefore
must never leave the chunker, and must never leave the provider either.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.memory.chunker import TextChunker
from agent.memory.embedding.provider import BLANK_INPUT_PLACEHOLDER, OpenAIEmbeddingProvider


class TestChunkTextBlankChunks(unittest.TestCase):
    """chunk_text flushes the accumulated lines when it meets an over-long
    line; a lone blank line at that boundary used to be emitted as an empty
    chunk."""

    def setUp(self):
        self.c = TextChunker()
        # max_chars = max_tokens(500) * chars_per_token(4)
        self.long_a = "A" * 2500
        self.long_b = "B" * 2500

    def _assert_no_blank(self, chunks):
        self.assertTrue(chunks)
        for ch in chunks:
            self.assertTrue(ch.text.strip(), "chunk_text must not emit blank chunks")

    def test_blank_line_between_two_long_lines(self):
        chunks = self.c.chunk_text(f"{self.long_a}\n\n{self.long_b}")
        self._assert_no_blank(chunks)

    def test_long_line_with_trailing_newline(self):
        chunks = self.c.chunk_text(f"{self.long_a}\n")
        self._assert_no_blank(chunks)

    def test_leading_blank_line_before_long_line(self):
        chunks = self.c.chunk_text(f"\n{self.long_a}")
        self._assert_no_blank(chunks)

    def test_content_is_preserved(self):
        text = f"{self.long_a}\n\n{self.long_b}"
        joined = "".join(ch.text for ch in self.c.chunk_text(text))
        self.assertEqual(joined.count("A"), len(self.long_a))
        self.assertEqual(joined.count("B"), len(self.long_b))

    def test_normal_text_is_untouched(self):
        chunks = self.c.chunk_text("第一行\n第二行\n第三行")
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].text, "第一行\n第二行\n第三行")


class TestSanitizeEmbeddingInput(unittest.TestCase):
    """The provider is the last stop before the wire, so it substitutes rather
    than drops: callers index the returned vectors positionally."""

    def setUp(self):
        self.sanitize = OpenAIEmbeddingProvider._sanitize_input

    def test_blank_items_replaced_in_place(self):
        self.assertEqual(
            self.sanitize(["hello", "", "  \n ", "world"]),
            ["hello", BLANK_INPUT_PLACEHOLDER, BLANK_INPUT_PLACEHOLDER, "world"],
        )

    def test_single_blank_string_replaced(self):
        self.assertEqual(self.sanitize(""), BLANK_INPUT_PLACEHOLDER)

    def test_non_blank_input_untouched(self):
        self.assertEqual(self.sanitize(["a", "b"]), ["a", "b"])
        self.assertEqual(self.sanitize("a"), "a")


if __name__ == "__main__":
    unittest.main()
