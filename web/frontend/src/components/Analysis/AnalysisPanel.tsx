/** Tabbed analysis side panel. */

import { useState } from "react";
import { ImbalancesTab } from "./ImbalancesTab";
import { TacticsTab } from "./TacticsTab";
import { EngineTab } from "./EngineTab";
import type { AnalysisResult } from "../../api/types";

interface Props {
  analysis: AnalysisResult | null;
  loading: boolean;
  error: string | null;
}

const TABS = ["Imbalances", "Tactics", "Engine"] as const;
type Tab = (typeof TABS)[number];

export function AnalysisPanel({ analysis, loading, error }: Props) {
  const [tab, setTab] = useState<Tab>("Imbalances");

  return (
    <div className="analysis-panel">
      <div className="analysis-tabs">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`analysis-tab ${tab === t ? "active" : ""}`}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="analysis-content">
        {loading && <div className="analysis-loading pulse">Analyzing position...</div>}
        {error && <div className="analysis-error">{error}</div>}
        {!loading && !error && analysis && (
          <>
            {tab === "Imbalances" && <ImbalancesTab analysis={analysis} />}
            {tab === "Tactics" && <TacticsTab tactics={analysis.tactics} />}
            {tab === "Engine" && <EngineTab analysis={analysis} />}
          </>
        )}
      </div>
    </div>
  );
}
