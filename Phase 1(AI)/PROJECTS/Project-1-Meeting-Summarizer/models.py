from pydantic import BaseModel
from typing import Optional


class ActionItem(BaseModel):
    task: str
    owner: Optional[str] = None
    deadline: Optional[str] = None


class Decision(BaseModel):
    description: str
    rationale: Optional[str] = None


class KeyPoint(BaseModel):
    topic: str
    detail: str


class MeetingSummary(BaseModel):
    title: str
    date: str = "Unknown"
    attendees: list[str]
    summary: str
    key_points: list[KeyPoint]
    action_items: list[ActionItem]
    decisions: list[Decision]
