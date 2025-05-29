from urllib.parse import urlparse, parse_qs
from typing import Tuple, Optional, Dict, Literal

# Define type literals for clarity
ContextType = Literal["recruit", "community", "unknown"] # 초빙, 커뮤니티 등
QueryType = Literal["job_posting_question", "user_profile_question", "general_question", "unknown"]

class RequestContext:
    def __init__(self,
                 raw_query: str,
                 url: Optional[str] = None,
                 board_id: Optional[str] = None,
                 is_detail_view: bool = False,
                 source_context: ContextType = "unknown",
                 query_type: QueryType = "unknown"):
        self.raw_query = raw_query # The user's actual text query
        self.url = url # The URL from which the agent request originated
        self.board_id = board_id # Parsed board_id if applicable
        self.is_detail_view = is_detail_view # True if board_id is present and relevant
        self.source_context = source_context # e.g., "recruit" (초빙), "community"
        self.query_type = query_type # e.g., "job_posting_question"

    def __repr__(self):
        return (f"RequestContext(raw_query='{self.raw_query}', url='{self.url}', "
                f"board_id='{self.board_id}', is_detail_view={self.is_detail_view}, "
                f"source_context='{self.source_context}', query_type='{self.query_type}')")

def parse_url_context(url: Optional[str]) -> Tuple[Optional[str], ContextType, bool]:
    """
    Parses a URL to extract board_id and determine context (초빙/비초빙) and if it's a detail view.
    Example URL: "www.medigate.net/recruit/1172769" -> board_id="1172769", context="recruit", is_detail=True
    Example URL: "www.medigate.net/recruit" -> board_id=None, context="recruit", is_detail=False
    """
    if not url:
        return None, "unknown", False

    parsed_url = urlparse(url)
    path_parts = [part for part in parsed_url.path.split('/') if part] # Filter out empty parts

    board_id: Optional[str] = None
    context: ContextType = "unknown"
    is_detail_view: bool = False

    if "recruit" in path_parts:
        context = "recruit"
        try:
            recruit_idx = path_parts.index("recruit")
            if len(path_parts) > recruit_idx + 1 and path_parts[recruit_idx + 1].isdigit():
                board_id = path_parts[recruit_idx + 1]
                is_detail_view = True
        except (ValueError, IndexError):
            pass
    
    return board_id, context, is_detail_view

def classify_query_type(query_text: str) -> QueryType:
    """
    Placeholder function to classify the type of query.
    """
    query_lower = query_text.lower()
    if any(kw in query_lower for kw in ["공고", "채용", "자리", "job", "posting", "연봉", "월급", "salary"]):
        return "job_posting_question"
    elif any(kw in query_lower for kw in ["나", "내 프로필", "내 정보", "my profile", "내 이력", "내 경험", "my experience", "내 조건"]):
        return "user_profile_question"
    elif not query_text.strip():
        return "unknown"
    return "general_question"

def analyze_request(raw_query: str, url: Optional[str]) -> RequestContext:
    """
    Analyzes the raw user query and URL to build a RequestContext object.
    """
    board_id, source_context, is_detail_view = parse_url_context(url)
    query_type = classify_query_type(raw_query)
    
    return RequestContext(
        raw_query=raw_query,
        url=url,
        board_id=board_id,
        is_detail_view=is_detail_view,
        source_context=source_context,
        query_type=query_type
    )
