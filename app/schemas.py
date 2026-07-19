from pydantic import BaseModel, Field


class DiscoveryRequest(BaseModel):
    categories: list[str] = Field(min_length=1, max_length=20)
    cities: list[str] = Field(min_length=1, max_length=20)
    minimum_rating: float = Field(default=4.0, ge=0, le=5)
    minimum_reviews: int = Field(default=10, ge=0)
    include_no_website: bool = True
    include_outdated_website: bool = True
    max_businesses: int = Field(default=20, ge=1, le=200)


class LeadDecision(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class EmailDraftRequest(BaseModel):
    recipient: str
    sender_name: str = Field(min_length=2, max_length=120)
    sender_business: str = Field(min_length=2, max_length=160)
    sender_address: str = Field(min_length=5, max_length=300)
    unsubscribe_email: str


class PauseRequest(BaseModel):
    paused: bool
    reason: str | None = Field(default=None, max_length=500)


class PublishRequest(BaseModel):
    repository_visibility: str = Field(default="private", pattern="^(private|public)$")
    deploy_to_vercel: bool = True
