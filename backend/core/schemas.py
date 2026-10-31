from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Body):
    # Retain the existing wire key; its value may be a legacy username.
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_identifier(cls, value):
        value = value.strip().lower()
        if not value:
            raise ValueError("Username or email is required")
        return value


class Credentials(Body):
    email: str | None = Field(default=None, min_length=3, max_length=254)
    username: str | None = Field(default=None, min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        if value is None:
            return None
        value = value.strip().lower()
        if not value:
            return None
        if (
            value.count("@") != 1
            or any(c.isspace() for c in value)
            or not all(value.split("@"))
            or "." not in value.split("@")[1]
        ):
            raise ValueError("Invalid email address")
        return value

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value):
        if value is None:
            return None
        value = value.strip().lower()
        if not value:
            return None
        if not all(c.isalnum() or c in "._-" for c in value):
            raise ValueError("Username may contain letters, digits, dot, dash and underscore")
        return value

    @model_validator(mode="after")
    def require_identifier(self):
        if self.email is None and self.username is None:
            raise ValueError("An email or username is required")
        return self


class Register(Credentials):
    timezone: str = "Asia/Shanghai"
    invitation_code: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("An IANA timezone is required")
        return value

    @field_validator("invitation_code")
    @classmethod
    def normalize_code(cls, value):
        return value.strip() if value is not None else None


class DeckCreate(Body):
    name: str = Field(min_length=1, max_length=200)
    parent_id: UUID | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError("Deck name cannot be blank")
        return value.strip()


class DeckUpdate(DeckCreate):
    pass


class NoteCreate(Body):
    card_template_key: str | None = Field(default=None, min_length=1, max_length=80)
    note_type_key: Literal["vocabulary", "sentence"]
    fields: dict[str, str | None]
    tags: list[str] = Field(default_factory=list, max_length=100)
    deck_id: UUID
    guid: str | None = Field(default=None, min_length=1, max_length=100)


class NoteUpdate(Body):
    revision: int = Field(ge=1)
    fields: dict[str, str | None]
    tags: list[str] | None = Field(default=None, max_length=100)


class Generate(Body):
    deck_id: UUID


class Confirm(Body):
    confirmation_token: str = Field(min_length=1, max_length=4096)


class TypePreview(Body):
    target_note_type_key: Literal["vocabulary", "sentence"]


class TypeChange(Confirm):
    revision: int = Field(ge=1)
    target_note_type_key: Literal["vocabulary", "sentence"]
    field_mapping: dict[str, str | None]
    field_values: dict[str, str | None] = Field(default_factory=dict)
    deck_id: UUID | None = None


class PasswordChange(Body):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


class DisableAccount(Body):
    password: str = Field(min_length=1, max_length=128)


class DeckMembership(Body):
    joined: bool


class LibraryImport(Body):
    note_guids: list[str] | None = Field(default=None, max_length=5000)
