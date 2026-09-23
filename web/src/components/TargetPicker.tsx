import { useState } from "react";

const PRESETS = [
  { target: "game.ali213.net", desc: "4xx 异常洪峰" },
  { target: "api2.xs2027.cn", desc: "5xx 源站故障" },
  { target: "kk331dsdi32onew.liu6t.cn", desc: "源站过载" },
];

interface Props {
  onStart: (target: string) => void;
  disabled: boolean;
}

export function TargetPicker({ onStart, disabled }: Props) {
  const [target, setTarget] = useState("");
  const [custom, setCustom] = useState("");

  const pick = (t: string) => {
    setTarget(t);
    setCustom("");
  };

  const submit = () => {
    const t = (custom || target).trim();
    if (t && !disabled) onStart(t);
  };

  return (
    <div className="targetbar">
      {PRESETS.map((p) => (
        <button
          key={p.target}
          type="button"
          className={"preset" + (target === p.target ? " active" : "")}
          onClick={() => pick(p.target)}
          disabled={disabled}
        >
          <span className="tag">{p.target}</span>
          <span className="desc">{p.desc}</span>
        </button>
      ))}
      <div className="target-custom">
        <input
          type="text"
          placeholder="或输入自定义域名 / IP"
          value={custom}
          onChange={(e) => {
            setCustom(e.target.value);
            setTarget("");
          }}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          disabled={disabled}
        />
        <button
          type="button"
          className="btn"
          onClick={submit}
          disabled={disabled || !(custom.trim() || target)}
        >
          开始调查
        </button>
      </div>
    </div>
  );
}
