from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

Message = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000),
]


class ActionType(StrEnum):
    QUERY = "query"
    CREATE_WORK_ORDER = "create_work_order"


class ObjectType(StrEnum):
    INVENTORY = "inventory"
    EQUIPMENT = "equipment"


class OperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message: Message
    requested_action: ActionType | None = None
    object_type: ObjectType | None = None
    object_id: (
        Annotated[
            str,
            StringConstraints(
                strip_whitespace=True,
                min_length=1,
                max_length=64,
                pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
            ),
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def require_complete_object_reference(self) -> Self:
        if (self.object_type is None) != (self.object_id is None):
            raise ValueError("object_type and object_id must be provided together")
        return self
