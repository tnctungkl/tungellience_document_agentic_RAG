import re
import unicodedata


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTIPLE_SPACES = re.compile(r"[ \t]+")
_THREE_OR_MORE_NEWLINES = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """Normalize Unicode and whitespace while preserving paragraph boundaries."""
    normalized = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    normalized = _CONTROL_CHARS.sub("", normalized)
    normalized = _MULTIPLE_SPACES.sub(" ", normalized)
    normalized = "\n".join(line.strip() for line in normalized.split("\n"))
    normalized = _THREE_OR_MORE_NEWLINES.sub("\n\n", normalized)
    return normalized.strip()
