from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class EmailInput(BaseModel):
    email: str = Field(max_length=254)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if value.count("@") != 1 or not all(value.split("@")) or any(c.isspace() for c in value):
            raise ValueError("Enter a valid email address")
        return value


class LoginInput(EmailInput):
    password: str = Field(min_length=1, max_length=128)


class RegisterInput(EmailInput):
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=128)
    workspace_name: str = Field(min_length=1, max_length=100)

    @field_validator("display_name", "workspace_name")
    @classmethod
    def nonblank(cls, value: str):
        if not value.strip():
            raise ValueError("This field cannot be blank")
        return value.strip()


class PasswordInput(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class NameInput(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=r"\S")


class InviteInput(EmailInput):
    role: Literal["ADMIN", "MEMBER"] = "MEMBER"


class AcceptInput(BaseModel):
    token: str = Field(min_length=20, max_length=100)


class RoleInput(BaseModel):
    role: Literal["OWNER", "ADMIN", "MEMBER"]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    display_name: str


class WorkspaceRead(BaseModel):
    id: int
    name: str
    slug: str
    role: Literal["OWNER", "ADMIN", "MEMBER"]


class SessionRead(BaseModel):
    user: UserRead
    workspaces: list[WorkspaceRead]
    active_workspace_id: int
    csrf_token: str
