"""Topic index and cross-corpus search (syntopic reading primitive)."""

from .catalog import TOPIC_CATALOG, TopicCategory
from .inverted import SearchIndex
from .search import SearchResult, search_corpus
from .topic_extract import extract_topics

__all__ = [
    "TOPIC_CATALOG",
    "SearchIndex",
    "SearchResult",
    "TopicCategory",
    "extract_topics",
    "search_corpus",
]
