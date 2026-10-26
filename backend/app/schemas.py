from pydantic import BaseModel, EmailStr, Field


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    name: str = ""


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    token: str
    user: dict


class ProfileIn(BaseModel):
    headline: str | None = None
    cv_text: str | None = None
    experience_text: str | None = Field(default=None, max_length=60000)
    target_date: str | None = Field(default=None, pattern=r"^(\d{4}-\d{2})?$")
    years_experience: int | None = None
    min_level: str | None = None
    locations: list[str] | None = None
    remote_ok: bool | None = None
    needs_sponsorship: bool | None = None
    excluded_title_terms: list[str] | None = None


class TagMatchIn(BaseModel):
    match: float = Field(ge=0, le=1)
    evidence: str = ""


class PostingIn(BaseModel):
    company: str
    title: str
    url: str
    location: str = ""
    remote_flag: str = "unstated"
    bay_area: bool = False
    pay_range: str = ""
    description: str = ""


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
