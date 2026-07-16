from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from opercerta.domain.errors import InventoryNotFound
from opercerta.domain.replenishment import (
    InventoryEvidence,
    PolicyEvidence,
    Sku,
    Version,
)


class _InventorySeedItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sku: Sku
    on_hand_quantity: StrictInt
    reserved_quantity: StrictInt

    @field_validator("on_hand_quantity", "reserved_quantity")
    @classmethod
    def require_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("inventory quantities must be non-negative")
        return value


class _InventorySeed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_version: Version
    items: tuple[_InventorySeedItem, ...]

    @model_validator(mode="after")
    def require_unique_skus(self) -> "_InventorySeed":
        skus = [item.sku for item in self.items]
        if len(skus) != len(set(skus)):
            raise ValueError("inventory seed contains duplicate SKU")
        return self


class _PolicySeedItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sku: Sku
    reorder_point: StrictInt
    target_stock: StrictInt
    minimum_order_quantity: StrictInt
    maximum_order_quantity: StrictInt
    evidence_ttl_seconds: StrictInt
    approval_required: StrictBool

    @field_validator(
        "reorder_point",
        "target_stock",
        "minimum_order_quantity",
        "maximum_order_quantity",
        "evidence_ttl_seconds",
    )
    @classmethod
    def require_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("policy integers must be non-negative")
        return value

    @model_validator(mode="after")
    def require_safe_policy(self) -> "_PolicySeedItem":
        if self.target_stock <= self.reorder_point:
            raise ValueError("target_stock must be greater than reorder_point")
        if self.minimum_order_quantity < 1:
            raise ValueError("minimum_order_quantity must be positive")
        if self.maximum_order_quantity < self.minimum_order_quantity:
            raise ValueError("maximum_order_quantity must be at least minimum_order_quantity")
        if self.evidence_ttl_seconds < 1:
            raise ValueError("evidence_ttl_seconds must be positive")
        if self.approval_required is not True:
            raise ValueError("approval_required must be true")
        return self


class _PolicySeed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_version: Version
    rule_version: Version
    items: tuple[_PolicySeedItem, ...]

    @model_validator(mode="after")
    def require_unique_skus(self) -> "_PolicySeed":
        skus = [item.sku for item in self.items]
        if len(skus) != len(set(skus)):
            raise ValueError("policy seed contains duplicate SKU")
        return self


class SyntheticCatalog:
    def __init__(
        self,
        inventory: _InventorySeed,
        policies: _PolicySeed,
        id_factory: Callable[[], UUID],
    ) -> None:
        inventory_by_sku = {item.sku: item for item in inventory.items}
        policies_by_sku = {item.sku: item for item in policies.items}
        if inventory_by_sku.keys() != policies_by_sku.keys():
            raise ValueError("inventory and policy seed SKUs must match")
        self._inventory_source_version = inventory.source_version
        self._rule_version = policies.rule_version
        self._inventory = inventory_by_sku
        self._policies = policies_by_sku
        self._id_factory = id_factory

    @classmethod
    def load(
        cls,
        inventory_path: Path,
        policy_path: Path,
        *,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> "SyntheticCatalog":
        inventory = _InventorySeed.model_validate_json(inventory_path.read_text(encoding="utf-8"))
        policies = _PolicySeed.model_validate_json(policy_path.read_text(encoding="utf-8"))
        return cls(inventory, policies, id_factory)

    @property
    def skus(self) -> frozenset[str]:
        return frozenset(self._inventory)

    def inventory_snapshot(
        self,
        sku: str,
        captured_at: datetime,
    ) -> InventoryEvidence:
        try:
            item = self._inventory[sku]
        except KeyError:
            raise InventoryNotFound from None
        return InventoryEvidence(
            evidence_id=self._id_factory(),
            sku=item.sku,
            on_hand_quantity=item.on_hand_quantity,
            reserved_quantity=item.reserved_quantity,
            captured_at=captured_at,
            source_version=self._inventory_source_version,
        )

    def policy_constraints(
        self,
        sku: str,
        captured_at: datetime,
    ) -> PolicyEvidence:
        try:
            item = self._policies[sku]
        except KeyError:
            raise InventoryNotFound from None
        return PolicyEvidence(
            evidence_id=self._id_factory(),
            action="replenish_inventory",
            sku=item.sku,
            reorder_point=item.reorder_point,
            target_stock=item.target_stock,
            minimum_order_quantity=item.minimum_order_quantity,
            maximum_order_quantity=item.maximum_order_quantity,
            evidence_ttl_seconds=item.evidence_ttl_seconds,
            approval_required=True,
            rule_version=self._rule_version,
            captured_at=captured_at,
        )

    def replace_inventory(
        self,
        sku: str,
        *,
        on_hand_quantity: int,
        reserved_quantity: int,
    ) -> None:
        if sku not in self._inventory:
            raise InventoryNotFound
        self._inventory[sku] = _InventorySeedItem(
            sku=sku,
            on_hand_quantity=on_hand_quantity,
            reserved_quantity=reserved_quantity,
        )
