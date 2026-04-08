import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import ForecastChart from "../components/ForecastChart";
import ScoreProfile from "../components/ScoreProfile";

export default function Analytics() {
  const [warehouseId, setWarehouseId] = useState("");
  const [period, setPeriod] = useState(7);

  const { data: forecastData } = useQuery({
    queryKey: ["forecasts", warehouseId],
    queryFn: () => api.getForecasts(warehouseId),
    enabled: !!warehouseId,
  });

  const { data: metricsData } = useQuery({
    queryKey: ["metrics", warehouseId, period],
    queryFn: () => api.getMetrics(warehouseId, period),
    enabled: !!warehouseId,
  });

  const { data: scoreData } = useQuery({
    queryKey: ["score-profile", warehouseId],
    queryFn: () => api.getScoreProfile(warehouseId),
    enabled: !!warehouseId,
  });

  const metrics = metricsData?.metrics;

  return (
    <div>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 16 }}>Analytics</h1>

      <div style={{ display: "flex", gap: 12, marginBottom: 24, alignItems: "center" }}>
        <input
          placeholder="Warehouse ID"
          value={warehouseId}
          onChange={(e) => setWarehouseId(e.target.value)}
          style={{ padding: "8px 12px", border: "1px solid #cbd5e1", borderRadius: 6, fontSize: 13 }}
        />
        <div style={{ display: "flex", gap: 4 }}>
          {[7, 14, 30].map((d) => (
            <button
              key={d}
              onClick={() => setPeriod(d)}
              style={{
                padding: "6px 14px",
                border: "none",
                borderRadius: 6,
                cursor: "pointer",
                fontSize: 12,
                fontWeight: 600,
                background: period === d ? "#3b82f6" : "#e2e8f0",
                color: period === d ? "#fff" : "#334155",
              }}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {!warehouseId && <p style={{ color: "#64748b" }}>Enter a warehouse ID to view analytics.</p>}

      {warehouseId && (
        <div style={{ display: "grid", gap: 24 }}>
          <div style={cardStyle}>
            <h2 style={cardTitle}>Forecast vs Actuals</h2>
            {forecastData?.forecasts?.length ? (
              <ForecastChart forecasts={forecastData.forecasts} />
            ) : (
              <p style={{ color: "#94a3b8" }}>No forecast data available.</p>
            )}
          </div>

          <div style={cardStyle}>
            <h2 style={cardTitle}>Business Metrics</h2>
            {metrics ? (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 16 }}>
                <MetricCard label="Fleet Utilization" value={`${(metrics.fleet_utilization_rate * 100).toFixed(1)}%`} />
                <MetricCard label="Miss Rate" value={`${(metrics.miss_rate * 100).toFixed(1)}%`} />
                <MetricCard label="Idle Vehicle Rate" value={`${(metrics.idle_vehicle_rate * 100).toFixed(1)}%`} />
                <MetricCard label="Lead Time Adherence" value={`${(metrics.lead_time_adherence * 100).toFixed(1)}%`} />
                <MetricCard label="Total Orders" value={String(metrics.total_orders)} />
              </div>
            ) : (
              <p style={{ color: "#94a3b8" }}>No metrics available.</p>
            )}
          </div>

          <div style={cardStyle}>
            <h2 style={cardTitle}>Score Profile</h2>
            {scoreData?.decisions?.length ? (
              <ScoreProfile decisions={scoreData.decisions} />
            ) : (
              <p style={{ color: "#94a3b8" }}>No optimizer decisions available.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ background: "#f1f5f9", padding: 16, borderRadius: 8, textAlign: "center" }}>
      <div style={{ fontSize: 24, fontWeight: 700, color: "#1e293b" }}>{value}</div>
      <div style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>{label}</div>
    </div>
  );
}

const cardStyle: React.CSSProperties = {
  background: "#fff",
  borderRadius: 12,
  padding: 24,
  boxShadow: "0 1px 3px rgba(0,0,0,0.08)",
};

const cardTitle: React.CSSProperties = {
  fontSize: 16,
  fontWeight: 600,
  marginBottom: 16,
  color: "#1e293b",
};
