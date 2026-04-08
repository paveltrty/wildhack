import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, Vehicle } from "../api/client";

export default function Fleet() {
  const qc = useQueryClient();
  const [warehouseId, setWarehouseId] = useState("");
  const [newType, setNewType] = useState<"gazel" | "fura">("fura");

  const { data: vehicles = [] } = useQuery({
    queryKey: ["vehicles", warehouseId],
    queryFn: () => api.getVehicles(warehouseId || undefined),
    refetchInterval: 30_000,
  });

  const addVehicle = useMutation({
    mutationFn: () => api.createVehicle(warehouseId, newType),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["vehicles"] }),
  });

  const returnVehicle = useMutation({
    mutationFn: (id: string) => api.returnVehicle(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["vehicles"] }),
  });

  const grouped = vehicles.reduce<Record<string, Vehicle[]>>((acc, v) => {
    const key = v.warehouse_id;
    if (!acc[key]) acc[key] = [];
    acc[key].push(v);
    return acc;
  }, {});

  return (
    <div>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 16 }}>Fleet Management</h1>

      <div style={{ display: "flex", gap: 12, marginBottom: 24, alignItems: "center", flexWrap: "wrap" }}>
        <input
          placeholder="Warehouse ID"
          value={warehouseId}
          onChange={(e) => setWarehouseId(e.target.value)}
          style={inputStyle}
        />
        <select value={newType} onChange={(e) => setNewType(e.target.value as "gazel" | "fura")} style={inputStyle}>
          <option value="fura">Fura</option>
          <option value="gazel">Gazel</option>
        </select>
        <button
          onClick={() => addVehicle.mutate()}
          disabled={!warehouseId}
          style={{ ...btnStyle, opacity: warehouseId ? 1 : 0.5 }}
        >
          Add Vehicle
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: 20 }}>
        {Object.entries(grouped).map(([wId, vehs]) => {
          const free = vehs.filter((v) => v.status === "free").length;
          const busy = vehs.filter((v) => v.status === "busy").length;
          return (
            <div key={wId} style={cardStyle}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12 }}>
                <h3 style={{ fontSize: 16, fontWeight: 700 }}>Warehouse {wId}</h3>
                <div style={{ fontSize: 13 }}>
                  <span style={{ color: "#22c55e", fontWeight: 600 }}>{free} free</span>
                  {" / "}
                  <span style={{ color: "#f59e0b", fontWeight: 600 }}>{busy} busy</span>
                </div>
              </div>
              {vehs.map((v) => (
                <div
                  key={v.id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "8px 0",
                    borderTop: "1px solid #f1f5f9",
                    fontSize: 13,
                  }}
                >
                  <div>
                    <span style={{ fontWeight: 600 }}>{v.vehicle_type}</span>
                    <span
                      style={{
                        marginLeft: 8,
                        padding: "1px 6px",
                        borderRadius: 8,
                        fontSize: 11,
                        fontWeight: 600,
                        color: "#fff",
                        background: v.status === "free" ? "#22c55e" : "#f59e0b",
                      }}
                    >
                      {v.status}
                    </span>
                    {v.eta_return && (
                      <span style={{ marginLeft: 8, color: "#64748b", fontSize: 11 }}>
                        ETA: {new Date(v.eta_return).toLocaleTimeString()}
                      </span>
                    )}
                  </div>
                  {v.status === "busy" && (
                    <button onClick={() => returnVehicle.mutate(v.id)} style={{ ...btnSmall, background: "#22c55e" }}>
                      Return
                    </button>
                  )}
                </div>
              ))}
            </div>
          );
        })}
      </div>

      {Object.keys(grouped).length === 0 && <p style={{ color: "#64748b" }}>No vehicles found.</p>}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  padding: "8px 12px",
  border: "1px solid #cbd5e1",
  borderRadius: 6,
  fontSize: 13,
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

const btnSmall: React.CSSProperties = {
  padding: "3px 10px",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: 11,
  fontWeight: 600,
};

const cardStyle: React.CSSProperties = {
  background: "#fff",
  borderRadius: 12,
  padding: 20,
  boxShadow: "0 1px 3px rgba(0,0,0,0.08)",
};
