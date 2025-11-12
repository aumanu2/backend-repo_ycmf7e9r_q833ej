import os
from datetime import datetime, timezone, date
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

from database import db, create_document, get_documents
from schemas import User, Challenge, Lesson, Progress, Message

app = FastAPI(title="LearnIn30Days API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "LearnIn30Days Backend is running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


# ---------- Utilities ----------

def _collection(name: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    return db[name]


def _now():
    return datetime.now(timezone.utc)


# ---------- User & Leaderboard ----------

class UpsertUser(BaseModel):
    name: str
    email: EmailStr
    avatar_url: Optional[str] = None


@app.post("/api/users")
def create_or_get_user(payload: UpsertUser):
    users = _collection("user")
    doc = users.find_one({"email": payload.email})
    if doc:
        return {"ok": True, "user": _sanitize(doc)}
    user = User(
        name=payload.name,
        email=payload.email,
        avatar_url=payload.avatar_url,
    )
    _id = create_document("user", user)
    created = users.find_one({"_id": _to_oid(_id)}) or users.find_one({"email": payload.email})
    return {"ok": True, "user": _sanitize(created)}


@app.get("/api/leaderboard")
def leaderboard(limit: int = 10):
    users = list(_collection("user").find().sort("points", -1).limit(limit))
    return {"ok": True, "leaders": [_sanitize(u) for u in users]}


# ---------- Challenges & Lessons ----------

@app.get("/api/challenges")
def list_challenges():
    items = get_documents("challenge")
    if not items:
        # Provide a couple of demo challenges when empty
        demo = [
            Challenge(
                title="AI Productivity in 30 Days",
                slug="ai-productivity",
                category="AI",
                difficulty="Beginner",
                description="Daily 5–10 min micro-lessons to automate workflows with AI.",
                cover_image=None,
                days=30,
            ),
            Challenge(
                title="Design Foundations in 30 Days",
                slug="design-foundations",
                category="Design",
                difficulty="Beginner",
                description="Master layout, typography, color and components with micro-tasks.",
                cover_image=None,
                days=30,
            ),
        ]
        for c in demo:
            try:
                create_document("challenge", c)
            except Exception:
                pass
        items = get_documents("challenge")
    return {"ok": True, "challenges": [_sanitize(i) for i in items]}


class CreateChallenge(BaseModel):
    title: str
    slug: str
    category: str
    difficulty: str = "Beginner"
    description: str
    cover_image: Optional[str] = None
    days: int = 30


@app.post("/api/challenges")
def create_challenge(payload: CreateChallenge):
    exists = _collection("challenge").find_one({"slug": payload.slug})
    if exists:
        raise HTTPException(status_code=400, detail="Challenge with this slug already exists")
    create_document("challenge", Challenge(**payload.model_dump()))
    return {"ok": True}


@app.get("/api/lessons/{slug}/{day}")
def get_lesson(slug: str, day: int):
    lesson = _collection("lesson").find_one({"challenge_slug": slug, "day": day})
    if not lesson:
        # generate a simple placeholder lesson for demo
        demo = Lesson(
            challenge_slug=slug,
            day=day,
            title=f"Day {day}: Micro-lesson",
            content=(
                "Today you will learn a concise concept and complete a small task. "
                "Spend 5–10 minutes reading, then do the task to lock in the learning."
            ),
            task="Write down 3 actionable steps you can apply today.",
        )
        create_document("lesson", demo)
        lesson = _collection("lesson").find_one({"challenge_slug": slug, "day": day})
    return {"ok": True, "lesson": _sanitize(lesson)}


# ---------- Progress & Gamification ----------

class CompletePayload(BaseModel):
    user_email: EmailStr
    challenge_slug: str
    day: int


@app.get("/api/progress/{email}/{slug}")
def get_progress(email: EmailStr, slug: str):
    doc = _collection("progress").find_one({"user_email": str(email), "challenge_slug": slug})
    if not doc:
        # initialize progress
        progress = Progress(user_email=str(email), challenge_slug=slug, current_day=1)
        create_document("progress", progress)
        doc = _collection("progress").find_one({"user_email": str(email), "challenge_slug": slug})
    return {"ok": True, "progress": _sanitize(doc)}


@app.post("/api/progress/complete")
def complete_day(payload: CompletePayload):
    users = _collection("user")
    prog_col = _collection("progress")
    user = users.find_one({"email": payload.user_email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    prog = prog_col.find_one({"user_email": payload.user_email, "challenge_slug": payload.challenge_slug})
    if not prog:
        progress = Progress(user_email=payload.user_email, challenge_slug=payload.challenge_slug)
        create_document("progress", progress)
        prog = prog_col.find_one({"user_email": payload.user_email, "challenge_slug": payload.challenge_slug})

    completed: List[int] = prog.get("completed_days", [])
    if payload.day not in completed:
        completed.append(payload.day)

    # Streak logic
    today = date.today()
    last_date_str = prog.get("last_completed_date")
    last_date = date.fromisoformat(last_date_str) if isinstance(last_date_str, str) else last_date_str
    streak = user.get("streak", 0)
    longest = user.get("longest_streak", 0)

    if last_date is None:
        streak = 1
    else:
        delta = (today - last_date).days
        if delta == 1:
            streak += 1
        elif delta == 0:
            # same day completion doesn't increase streak multiple times
            streak = max(1, streak)
        else:
            streak = 1
    longest = max(longest, streak)

    # Points: +10 per day completed, +5 bonus for 5-day streaks
    points = user.get("points", 0) + 10
    if streak % 5 == 0:
        points += 5

    # Update progress
    current_day = max(prog.get("current_day", 1), payload.day + 1)
    prog_col.update_one(
        {"_id": prog["_id"]},
        {"$set": {
            "completed_days": sorted(completed),
            "current_day": current_day,
            "last_completed_date": today.isoformat(),
            "updated_at": _now(),
        }}
    )

    # Update user stats
    users.update_one(
        {"_id": user["_id"]},
        {"$set": {"streak": streak, "longest_streak": longest, "points": points, "updated_at": _now()}}
    )

    updated_user = users.find_one({"_id": user["_id"]})
    updated_prog = prog_col.find_one({"_id": prog["_id"]})
    return {"ok": True, "user": _sanitize(updated_user), "progress": _sanitize(updated_prog)}


# ---------- Chat Assistant (simple, no external API required) ----------

class ChatRequest(BaseModel):
    user_email: EmailStr
    challenge_slug: str
    message: str


@app.post("/api/chat")
def chat_assistant(req: ChatRequest):
    # Simple heuristic assistant. For production integrate OpenAI.
    prompt = req.message.strip().lower()
    if any(k in prompt for k in ["stuck", "help", "clarify", "explain"]):
        reply = (
            "Here's a tip: break the task into a 5-minute action. Identify the smallest next step "
            "you can complete now. If the lesson mentions tools, summarize the 3 key commands "
            "or steps and try one. Want an example tailored to your role? Tell me your job title."
        )
    elif any(k in prompt for k in ["motivate", "motivation", "remind", "accountability"]):
        reply = (
            "You're doing great. Consistency over intensity wins in microlearning. "
            "Complete today's task and you'll add +10 points. Keep your streak alive!"
        )
    else:
        reply = (
            "Got it. In LearnIn30Days, each lesson is 5–10 minutes with a single task. "
            "Ask me about the concept, a quick checklist, or how to apply it to your project."
        )

    # Optionally store message history
    try:
        create_document("message", Message(user_email=req.user_email, role="user", content=req.message))
        create_document("message", Message(user_email=req.user_email, role="assistant", content=reply))
    except Exception:
        pass

    return {"ok": True, "reply": reply}


# ---------- Helpers ----------

from bson import ObjectId

def _to_oid(value: str):
    try:
        return ObjectId(value)
    except Exception:
        return value


def _sanitize(doc: dict):
    if not doc:
        return doc
    d = dict(doc)
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    return d


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
