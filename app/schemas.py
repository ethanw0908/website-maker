from pydantic import BaseModel, EmailStr, Field, model_validator


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


class LeadNoteRequest(BaseModel):
    content: str = Field(default="", max_length=5_000)


class EmailDraftRequest(BaseModel):
    recipient: EmailStr
    sender_name: str | None = Field(default=None, min_length=2, max_length=120)
    sender_business: str | None = Field(default=None, min_length=2, max_length=160)
    sender_address: str | None = Field(default=None, min_length=5, max_length=500)
    unsubscribe_email: EmailStr | None = None


class PauseRequest(BaseModel):
    paused: bool
    reason: str | None = Field(default=None, max_length=500)


class PublishRequest(BaseModel):
    repository_visibility: str = Field(default="private", pattern="^(private|public)$")
    deploy_to_vercel: bool = True


class SmtpSettingsRequest(BaseModel):
    host: str = Field(min_length=2, max_length=255)
    port: int = Field(default=587, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=320)
    password: str | None = Field(default=None, max_length=1_000)
    from_email: EmailStr
    from_name: str | None = Field(default=None, max_length=160)
    sender_business: str | None = Field(default=None, max_length=160)
    postal_address: str | None = Field(default=None, max_length=500)
    unsubscribe_email: EmailStr | None = None
    use_tls: bool = True
    use_ssl: bool = False
    enabled: bool = True

    @model_validator(mode="after")
    def validate_transport(self) -> "SmtpSettingsRequest":
        if self.use_tls and self.use_ssl:
            raise ValueError("Choose STARTTLS or SSL, not both")
        return self
