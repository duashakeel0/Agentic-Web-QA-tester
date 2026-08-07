import type { ModelChoice } from "../types/pipeline";
import "./ModelSelector.css";

const OPTIONS: { value: ModelChoice; label: string; hint: string }[] = [
  { value: "claude", label: "Claude", hint: "Higher accuracy, costs per call" },
  { value: "ollama", label: "Llama (Ollama)", hint: "Free, runs locally" },
  { value: "both", label: "Compare Both", hint: "Runs both side by side, 3 reports" },
];

function ModelSelector({
  value,
  onChange,
  disabled,
}: {
  value: ModelChoice;
  onChange: (value: ModelChoice) => void;
  disabled?: boolean;
}) {
  return (
    <div className="model-selector" role="radiogroup" aria-label="Model choice">
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          className={`model-option${value === option.value ? " selected" : ""}`}
          onClick={() => onChange(option.value)}
          disabled={disabled}
        >
          <span className="model-option-label">{option.label}</span>
          <span className="model-option-hint">{option.hint}</span>
        </button>
      ))}
    </div>
  );
}

export default ModelSelector;
