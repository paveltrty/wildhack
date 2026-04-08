import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, WarehouseConfig } from "../api/client";
import UploadModal from "../components/UploadModal";

export default function Settings() {
  const qc = useQueryClient();
  const [warehouseId, setWarehouseId] = useState("");
  const [showUpload, setShowUpload] = useState(false);

  const { data: config } = useQuery({
    queryKey: ["config", warehouseId],
    queryFn: () => api.getConfig(warehouseId),
    enabled: !!warehouseId,
    retry: false,
  });

  const [form, setForm] = useState<Partial<WarehouseConfig>>({});

  const handleLoad = useCallback(() => {
    if (config) {
      setForm({
        gazel_capacity: config.gazel_capacity,
        fura_capacity: config.fura_capacity,
        lead_time_min: config.lead_time_min,
        safety_factor: config.safety_factor,
        alpha: config.alpha,
        beta: config.beta,
        travel_buffer_min: config.travel_buffer_min,
      });
    }
  }, [config]);

  const save = useMutation({
    mutationFn: () => api.updateConfig(warehouseId, form),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["config", warehouseId] }),
  });

  return (
    <div>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 16 }}>Settings</h1>

      <div style={{ display: "flex", gap: 12, marginBottom: 24, alignItems: "center" }}>
        <input
          placeholder="Warehouse ID"
          value={warehouseId}
          onChange={(e) => setWarehouseId(e.target.value)}
          style={inputStyle}
        />
        <button onClick={handleLoad} disabled={!config} style={{ ...btnStyle, opacity: config ? 1 : 0.5 }}>
          Load Config
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        <div style={cardStyle}>
          <h2 style={cardTitle}>Warehouse Configuration</h2>

          <div style={{ display: "grid", gap: 16 }}>
            <Field label="Gazel Capacity (units)" value={form.gazel_capacity ?? 10} onChange={(v) => setForm({ ...form, gazel_capacity: v })} />
            <Field label="Fura Capacity (units)" value={form.fura_capacity ?? 40} onChange={(v) => setForm({ ...form, fura_capacity: v })} />
            <SliderField label="Lead Time (min)" min={15} max={180} step={5} value={form.lead_time_min ?? 60} onChange={(v) => setForm({ ...form, lead_time_min: v })} />
            <SliderField label="Safety Factor" min={1.0} max={1.5} step={0.05} value={form.safety_factor ?? 1.05} onChange={(v) => setForm({ ...form, safety_factor: v })} />
            <SliderField label="Miss Penalty (alpha)" min={0.5} max={0.9} step={0.05} value={form.alpha ?? 0.7} onChange={(v) => setForm({ ...form, alpha: v, beta: Math.round((1 - v) * 100) / 100 })} />
            <Field label="Overflow Penalty (beta = 1 - alpha)" value={form.beta ?? 0.3} onChange={() => {}} disabled />
            <Field label="Travel Buffer (min)" value={form.travel_buffer_min ?? 15} onChange={(v) => setForm({ ...form, travel_buffer_min: v })} />

            <button onClick={() => save.mutate()} disabled={!warehouseId} style={btnStyle}>
              Save Configuration
            </button>
          </div>
        </div>

        <div style={cardStyle}>
          <h2 style={cardTitle}>Upload Data</h2>
          <p style={{ fontSize: 13, color: "#64748b", marginBottom: 16 }}>
            Upload a parquet file containing shipment event data.
          </p>
          <button onClick={() => setShowUpload(true)} style={btnStyle}>
            Upload Parquet File
          </button>
        </div>
      </div>

      {showUpload && <UploadModal onClose={() => setShowUpload(false)} />}
    </div>
  );
}

function Field({ label, value, onChange, disabled }: { label: string; value: number; onChange: (v: number) => void; disabled?: boolean }) {
  return (
    <div>
      <label style={{ fontSize: 12, fontWeight: 600, color: "#475569", display: "block", marginBottom: 4 }}>{label}</label>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
        disabled={disabled}
        style={{ ...inputStyle, width: "100%", boxSizing: "border-box", background: disabled ? "#f1f5f9" : "#fff" }}
      />
    </div>
  );
}

function SliderField({ label, min, max, step, value, onChange }: { label: string; min: number; max: number; step: number; value: number; onChange: (v: number) => void }) {
  return (
    <div>
      <label style={{ fontSize: 12, fontWeight: 600, color: "#475569", display: "block", marginBottom: 4 }}>
        {label}: <strong>{value}</strong>
      </label>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        style={{ width: "100%" }}
      />
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  padding: "8px 12px",
  border: "1px solid #cbd5e1",
  borderRadius: 6,
  fontSize: 13,
  outline: "none",
};

const btnStyle: React.CSSProperties = {
  padding: "8px 16px",
  background: "#3b82f6",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: 13,
  fontWeight: 600,
};

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
