from pydantic import BaseModel, ConfigDict, Field


class RoleCreate(BaseModel):
    name: str = Field(max_length=50)
    description: str | None = None


class Role(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)

    @classmethod
    def from_model(cls, role) -> "Role":
        return cls(
            id=role.id,
            name=role.name,
            description=role.description,
            permissions=sorted(p.code for p in role.permissions),
        )


class Permission(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str


class RoleIdList(BaseModel):
    role_ids: list[int]


class PermissionCodeList(BaseModel):
    codes: list[str]
