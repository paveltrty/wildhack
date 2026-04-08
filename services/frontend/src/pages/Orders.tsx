import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, Order } from "../api/client";

const statusColors: Record<string, string> = {
  draft: "#94a3b8",
  approved: "#3b82f6",
  dispatched: "#f59e0b",
  completed: "#22c55e",
};

export default function Orders() {
  const qc = useQueryClient();
  const [warehouseId, setWarehouseId] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [completeId, setCompleteId] = useState<string | null>(null);
  const [actualShipments, setActualShipments] = useState("");

  const { data: orders = [], isLoading } = useQuery({
    queryKey: ["orders", warehouseId, statusFilter],
    queryFn: () => api.getOrders({ warehouse_id: warehouseId || undefined, status: statusFilter || undefined }),
    refetchInterval: 60_000,
  });

  const approve = useMutation({
    mutationFn: (id: string) => api.approveOrder(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["orders"] }),
  });

  const complete = useMutation({
    mutationFn: ({ id, val }: { id: string; val: number }) => api.completeOrder(id, val),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["orders"] });
      setCompleteId(null);
      setActualShipments("");
    },
  });

  return (
    <div>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 16 }}>Transport Orders</h1>

      <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
        <input
          placeholder="Warehouse ID"
          value={warehouseId}
          onChange={(e) => setWarehouseId(e.target.value)}
          style={inputStyle}
        />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={inputStyle}>
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="approved">Approved</option>
          <option value="dispatched">Dispatched</option>
          <option value="completed">Completed</option>
        </select>
      </div>

      {isLoading ? (
        <p>Loading...</p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#e2e8f0", textAlign: "left" }}>
                {["ID", "Warehouse", "Departure", "Type", "Count", "Capacity", "Horizon", "Score", "Status", "Actions"].map(
                  (h) => (
                    <th key={h} style={{ padding: "10px 12px", fontWeight: 600 }}>
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {orders.map((o: Order) => (
                <tr key={o.id} style={{ borderBottom: "1px solid #e2e8f0" }}>
                  <td style={cellStyle}>{o.id.slice(0, 8)}</td>
                  <td style={cellStyle}>{o.warehouse_id}</td>
                  <td style={cellStyle}>{new Date(o.scheduled_departure).toLocaleString()}</td>
                  <td style={cellStyle}>{o.vehicle_type}</td>
                  <td style={cellStyle}>{o.vehicle_count}</td>
                  <td style={cellStyle}>{o.capacity_units.toFixed(1)}</td>
                  <td style={cellStyle}>h{o.chosen_horizon}</td>
                  <td style={cellStyle}>{o.optimizer_score.toFixed(3)}</td>
                  <td style={cellStyle}>
                    <span
                      style={{
                        padding: "2px 8px",
                        borderRadius: 12,
                        fontSize: 12,
                        fontWeight: 600,
                        color: "#fff",
                        background: statusColors[o.status] || "#64748b",
                      }}
                    >
                      {o.status}
                    </span>
                  </td>
                  <td style={cellStyle}>
                    {o.status === "draft" && (
                      <button onClick={() => approve.mutate(o.id)} style={btnStyle}>
                        Approve
                      </button>
                    )}
                    {(o.status === "approved" || o.status === "dispatched") && (
                      <button onClick={() => setCompleteId(o.id)} style={{ ...btnStyle, background: "#22c55e" }}>
                        Complete
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {completeId && (
        <div style={modalOverlay}>
          <div style={modalBox}>
            <h3 style={{ marginBottom: 12 }}>Enter Actual Shipments</h3>
            <input
              type="number"
              value={actualShipments}
              onChange={(e) => setActualShipments(e.target.value)}
              placeholder="Actual shipments"
              style={inputStyle}
            />
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button
                onClick={() => complete.mutate({ id: completeId, val: parseFloat(actualShipments) || 0 })}
                style={btnStyle}
              >
                Submit
              </button>
              <button onClick={() => setCompleteId(null)} style={{ ...btnStyle, background: "#64748b" }}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
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

const cellStyle: React.CSSProperties = { padding: "10px 12px" };

const btnStyle: React.CSSProperties = {
  padding: "4px 12px",
  background: "#3b82f6",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: 12,
  fontWeight: 600,
};

const modalOverlay: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,0.4)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 1000,
};

const modalBox: React.CSSProperties = {
  background: "#fff",
  padding: 24,
  borderRadius: 12,
  minWidth: 320,
  boxShadow: "0 8px 32px rgba(0,0,0,0.2)",
};
