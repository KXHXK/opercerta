import { useState } from "react";

import { MASTERY_ITEMS } from "./engineering-content";

const STORAGE_KEY = "opercerta.engineering.mastery.v1";
const VALID_IDS = new Set<string>(MASTERY_ITEMS.map(([id]) => id));

function readCompleted(): string[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(value)
      ? value.filter(
          (item): item is string => typeof item === "string" && VALID_IDS.has(item),
        )
      : [];
  } catch {
    return [];
  }
}

export function MasteryChecklist() {
  const [completed, setCompleted] = useState(readCompleted);

  function toggle(id: string) {
    const next = completed.includes(id)
      ? completed.filter((item) => item !== id)
      : [...completed, id];
    setCompleted(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  }

  function reset() {
    localStorage.removeItem(STORAGE_KEY);
    setCompleted([]);
  }

  return (
    <section className="engineering-section mastery-section" aria-labelledby="mastery-title">
      <p className="section-kicker">LOCAL PRACTICE</p>
      <h2 id="mastery-title">掌握检查</h2>
      <p>只保存在当前浏览器，不上传、不进入公开专题，也不把勾选等同于已经精通。</p>
      <div className="mastery-list">
        {MASTERY_ITEMS.map(([id, label]) => (
          <label key={id}>
            <input
              type="checkbox"
              checked={completed.includes(id)}
              onChange={() => toggle(id)}
            />
            <span>{label}</span>
          </label>
        ))}
      </div>
      <button type="button" onClick={reset}>
        重置本地进度
      </button>
    </section>
  );
}
