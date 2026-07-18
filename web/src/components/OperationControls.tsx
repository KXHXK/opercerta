import { useState } from "react";

import type { DemoRole } from "../session";

type OperationControlsProps = {
  role: DemoRole;
  isAuthenticated: boolean;
  onRoleChange: (role: DemoRole) => void;
  onCreate: (sku: string) => void;
  onLoad: (operationId: string) => void;
};

export function OperationControls({
  role,
  isAuthenticated,
  onRoleChange,
  onCreate,
  onLoad
}: OperationControlsProps) {
  const [sku, setSku] = useState("SKU-LOW-001");
  const [operationId, setOperationId] = useState("");

  return (
    <section aria-label="操作控制区">
      <label className="field-label" htmlFor="demo-role">演示角色</label>
      <select id="demo-role" value={role} onChange={(event) => onRoleChange(event.target.value as DemoRole)}>
        <option value="operator">operator｜创建处置</option>
        <option value="approver">approver｜提交审批</option>
        <option value="auditor">auditor｜审计读取</option>
        <option value="demo-admin">demo-admin｜演示管理员</option>
      </select>

      <label className="field-label" htmlFor="demo-sku">库存 SKU</label>
      <select id="demo-sku" value={sku} onChange={(event) => setSku(event.target.value)}>
        <option value="SKU-LOW-001">SKU-LOW-001｜库存不足</option>
      </select>
      <button
        type="button"
        disabled={!isAuthenticated || role !== "operator"}
        onClick={() => onCreate(sku)}
      >
        创建补货处置
      </button>

      <label className="field-label" htmlFor="operation-id">处置编号</label>
      <div className="inline-fields">
        <input
          id="operation-id"
          value={operationId}
          onChange={(event) => setOperationId(event.target.value)}
          placeholder="粘贴 operation_id"
        />
        <button
          type="button"
          disabled={!isAuthenticated || operationId.trim().length === 0}
          onClick={() => onLoad(operationId.trim())}
        >
          读取处置
        </button>
      </div>
      <p className="panel-note">切换角色后会重新获取仅存于内存中的演示 JWT。</p>
    </section>
  );
}
