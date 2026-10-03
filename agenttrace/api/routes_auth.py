from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/auth", tags=["Authentication"])

class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    success: bool
    token: str
    user: dict

# Canonical Dummy Credentials for Reviewers & Evaluators
VALID_CREDENTIALS = [
    {
        "email": "investigator@agenttrace.io",
        "password": "agenttrace2026!",
        "role": "Lead Agent Investigator",
        "name": "Sarah Chen"
    },
    {
        "email": "demo@agenttrace.io",
        "password": "agenttrace2026!",
        "role": "Forensics Reviewer",
        "name": "Demo Reviewer"
    },
    {
        "email": "admin@agenttrace.io",
        "password": "agenttrace2026!",
        "role": "Platform Admin",
        "name": "Platform Admin"
    }
]

@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest):
    email = req.email.strip().lower()
    password = req.password.strip()

    user_match = next((u for u in VALID_CREDENTIALS if u["email"].lower() == email and u["password"] == password), None)
    
    # Also allow any user if password is "agenttrace2026!" or if reviewer types their own name with demo password
    if not user_match and password == "agenttrace2026!":
        user_match = {
            "email": email,
            "role": "Agent Evaluator",
            "name": email.split("@")[0].capitalize()
        }

    if not user_match:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. Please verify your email and password."
        )

    return {
        "success": True,
        "token": f"at_tok_{user_match['email'].replace('@', '_').replace('.', '_')}_session",
        "user": {
            "email": user_match["email"],
            "role": user_match["role"],
            "name": user_match["name"]
        }
    }

@router.get("/me")
def get_current_user(token: Optional[str] = None):
    # Dummy session introspection
    return {
        "authenticated": True,
        "email": "investigator@agenttrace.io",
        "role": "Lead Agent Investigator"
    }
