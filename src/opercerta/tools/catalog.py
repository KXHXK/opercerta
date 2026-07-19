from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from opercerta.domain.errors import EquipmentNotFound, InventoryNotFound
from opercerta.domain.maintenance import (
    AlertSeverity,
    EquipmentEvidence,
    EquipmentId,
    EquipmentState,
    MaintenancePolicyEvidence,
    PriorityMapping,
)
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


class _EquipmentSeedItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    equipment_id: EquipmentId
    state: EquipmentState
    alert_code: str | None
    severity: AlertSeverity
    last_heartbeat: datetime

    @field_validator("last_heartbeat")
    @classmethod
    def require_aware_heartbeat(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("last heartbeat must include timezone")
        return value

    @model_validator(mode="after")
    def require_consistent_alert(self) -> "_EquipmentSeedItem":
        if (self.alert_code is None) != (self.severity is AlertSeverity.NONE):
            raise ValueError("alert code and severity must be present together")
        return self


class _EquipmentSeed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_version: Version
    items: tuple[_EquipmentSeedItem, ...]

    @model_validator(mode="after")
    def require_unique_equipment(self) -> "_EquipmentSeed":
        identifiers = [item.equipment_id for item in self.items]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("equipment seed contains duplicate equipment ID")
        return self


class _MaintenancePolicySeedItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    equipment_id: EquipmentId
    allowed_alert_levels: tuple[Literal["warning", "critical"], ...]
    maximum_heartbeat_age_seconds: StrictInt
    priority_mapping: PriorityMapping
    evidence_ttl_seconds: StrictInt
    approval_required: StrictBool

    @model_validator(mode="after")
    def require_safe_policy(self) -> "_MaintenancePolicySeedItem":
        if not self.allowed_alert_levels or len(self.allowed_alert_levels) != len(
            set(self.allowed_alert_levels)
        ):
            raise ValueError("allowed alert levels must be non-empty and unique")
        if self.maximum_heartbeat_age_seconds < 1 or self.evidence_ttl_seconds < 1:
            raise ValueError("maintenance policy durations must be positive")
        if self.approval_required is not True:
            raise ValueError("approval_required must be true")
        return self


class _MaintenancePolicySeed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_version: Version
    rule_version: Version
    items: tuple[_MaintenancePolicySeedItem, ...]

    @model_validator(mode="after")
    def require_unique_equipment(self) -> "_MaintenancePolicySeed":
        identifiers = [item.equipment_id for item in self.items]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("maintenance policy seed contains duplicate equipment ID")
        return self


class SyntheticCatalog:
    def __init__(
        self,
        inventory: _InventorySeed,
        policies: _PolicySeed,
        id_factory: Callable[[], UUID],
        equipment: _EquipmentSeed | None = None,
        maintenance_policies: _MaintenancePolicySeed | None = None,
    ) -> None:
        inventory_by_sku = {item.sku: item for item in inventory.items}
        policies_by_sku = {item.sku: item for item in policies.items}
        if inventory_by_sku.keys() != policies_by_sku.keys():
            raise ValueError("inventory and policy seed SKUs must match")
        self._inventory_source_version = inventory.source_version
        self._rule_version = policies.rule_version
        self._inventory = inventory_by_sku
        self._policies = policies_by_sku
        if (equipment is None) != (maintenance_policies is None):
            raise ValueError("equipment and maintenance policy seeds must be provided together")
        equipment_by_id = (
            {item.equipment_id: item for item in equipment.items} if equipment is not None else {}
        )
        maintenance_by_id = (
            {item.equipment_id: item for item in maintenance_policies.items}
            if maintenance_policies is not None
            else {}
        )
        if equipment_by_id.keys() != maintenance_by_id.keys():
            raise ValueError("equipment and maintenance policy IDs must match")
        self._equipment_source_version = (
            equipment.source_version if equipment is not None else "unconfigured"
        )
        self._maintenance_rule_version = (
            maintenance_policies.rule_version
            if maintenance_policies is not None
            else "unconfigured"
        )
        self._equipment = equipment_by_id
        self._maintenance_policies = maintenance_by_id
        self._id_factory = id_factory

    @classmethod
    def load(
        cls,
        inventory_path: Path,
        policy_path: Path,
        *,
        equipment_path: Path | None = None,
        maintenance_policy_path: Path | None = None,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> "SyntheticCatalog":
        inventory = _InventorySeed.model_validate_json(inventory_path.read_text(encoding="utf-8"))
        policies = _PolicySeed.model_validate_json(policy_path.read_text(encoding="utf-8"))
        if (equipment_path is None) != (maintenance_policy_path is None):
            raise ValueError("equipment and maintenance policy paths must be provided together")
        equipment = (
            _EquipmentSeed.model_validate_json(equipment_path.read_text(encoding="utf-8"))
            if equipment_path is not None
            else None
        )
        maintenance_policies = (
            _MaintenancePolicySeed.model_validate_json(
                maintenance_policy_path.read_text(encoding="utf-8")
            )
            if maintenance_policy_path is not None
            else None
        )
        return cls(inventory, policies, id_factory, equipment, maintenance_policies)

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

    def equipment_status(
        self,
        equipment_id: str,
        captured_at: datetime,
    ) -> EquipmentEvidence:
        try:
            item = self._equipment[equipment_id]
        except KeyError:
            raise EquipmentNotFound from None
        return EquipmentEvidence(
            evidence_id=self._id_factory(),
            equipment_id=item.equipment_id,
            state=item.state,
            alert_code=item.alert_code,
            severity=item.severity,
            last_heartbeat=item.last_heartbeat,
            captured_at=captured_at,
            source_version=self._equipment_source_version,
        )

    def maintenance_policy_constraints(
        self,
        equipment_id: str,
        captured_at: datetime,
    ) -> MaintenancePolicyEvidence:
        try:
            item = self._maintenance_policies[equipment_id]
        except KeyError:
            raise EquipmentNotFound from None
        return MaintenancePolicyEvidence(
            evidence_id=self._id_factory(),
            action="repair_equipment",
            equipment_id=item.equipment_id,
            allowed_alert_levels=item.allowed_alert_levels,
            maximum_heartbeat_age_seconds=item.maximum_heartbeat_age_seconds,
            priority_mapping=item.priority_mapping,
            evidence_ttl_seconds=item.evidence_ttl_seconds,
            approval_required=True,
            rule_version=self._maintenance_rule_version,
            captured_at=captured_at,
        )

    def replace_equipment(
        self,
        equipment_id: str,
        *,
        state: EquipmentState,
        alert_code: str | None,
        severity: AlertSeverity,
        last_heartbeat: datetime,
    ) -> None:
        if equipment_id not in self._equipment:
            raise EquipmentNotFound
        self._equipment[equipment_id] = _EquipmentSeedItem(
            equipment_id=equipment_id,
            state=state,
            alert_code=alert_code,
            severity=severity,
            last_heartbeat=last_heartbeat,
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
