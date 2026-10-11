from pathlib import Path

from app.agent.document_analysis import DocumentAnalysisTool


def test_most_frequent_letter_supports_english_and_turkish() -> None:
    assert DocumentAnalysisTool.supports("What is the most frequent letter?")
    assert DocumentAnalysisTool.supports("Bana en çok geçen harfi söyle")


def test_most_frequent_letter_is_deterministic(tmp_path: Path) -> None:
    (tmp_path / "sample.txt").write_text("Merhaba aaaa!", encoding="utf-8")
    tool = DocumentAnalysisTool(tmp_path, 25)

    result = tool.analyze("Bana en çok geçen harfi söyle")

    assert result is not None
    assert result.operation == "most_frequent_letter"
    assert "a, appear" in result.answer or "a, appearing" in result.answer
    assert result.sources == ("sample.txt",)


def test_word_and_character_count(tmp_path: Path) -> None:
    (tmp_path / "sample.txt").write_text("one two\nthree", encoding="utf-8")
    tool = DocumentAnalysisTool(tmp_path, 25)

    assert "3 words" in tool.analyze("How many words are in the document?").answer
    assert "13 characters" in tool.analyze("What is the character count?").answer
