from pydantic import BaseModel
from typing import List, Optional

class AskRequest(BaseModel):
    query: str
    temporary: bool = False
    session_id: Optional[str] = None

class AskResponse(BaseModel):
    answer: str
    caveat: str
    evidence: Optional[List[str]] = []
    next_steps: Optional[List[str]] = []
