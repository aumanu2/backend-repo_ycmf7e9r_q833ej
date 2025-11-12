"""
Database Schemas for LearnIn30Days

Each Pydantic model corresponds to a MongoDB collection. The collection name
is the lowercase of the class name. Example: User -> "user".
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import date

class User(BaseModel):
    """User profile and gamification stats"""
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Unique email address")
    avatar_url: Optional[str] = Field(None, description="Profile avatar URL")
    points: int = Field(0, ge=0, description="Total gamification points")
    streak: int = Field(0, ge=0, description="Current daily completion streak")
    longest_streak: int = Field(0, ge=0, description="All-time longest streak")
    badges: List[str] = Field(default_factory=list, description="Unlocked badges")
    is_active: bool = Field(True, description="Whether the user is active")

class Challenge(BaseModel):
    """30-day challenge metadata"""
    title: str = Field(..., description="Challenge title")
    slug: str = Field(..., description="URL-friendly unique identifier")
    category: str = Field(..., description="Category like AI, design, marketing, productivity")
    difficulty: str = Field("Beginner", description="Difficulty level")
    description: str = Field(..., description="Short description of the challenge")
    cover_image: Optional[str] = Field(None, description="Cover image URL")
    days: int = Field(30, ge=1, le=60, description="Total days in the challenge")

class Lesson(BaseModel):
    """Daily micro-lesson content for a challenge/day"""
    challenge_slug: str = Field(..., description="Related challenge slug")
    day: int = Field(..., ge=1, le=60, description="Day number")
    title: str = Field(..., description="Lesson title")
    content: str = Field(..., description="Text-based micro-lesson content (5–10 min)")
    task: Optional[str] = Field(None, description="Actionable task for the day")

class Progress(BaseModel):
    """User's progress within a challenge"""
    user_email: EmailStr = Field(..., description="User email")
    challenge_slug: str = Field(..., description="Challenge slug")
    current_day: int = Field(1, ge=1, description="Current day user is on")
    completed_days: List[int] = Field(default_factory=list, description="List of completed day numbers")
    last_completed_date: Optional[date] = Field(None, description="Date of last completion (for streaks)")

class Message(BaseModel):
    """AI assistant chat message"""
    user_email: EmailStr = Field(...)
    role: str = Field(..., description="user or assistant")
    content: str = Field(..., description="Message text")
