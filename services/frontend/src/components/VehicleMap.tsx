import { Vehicle } from "../api/client";

interface Props {
  vehicles: Vehicle[];
}

export default function VehicleMap({ vehicles }: Props) {
  const free = vehicles.filter((v) => v.status === "free");
  const busy = vehicles.filter((v) => v.status === "busy");

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
      <div>
        <h4 style={{ fontSize: 14, fontWeight: 600, color: "#22c55e", marginBottom: 8 }}>
          Free ({free.length})
        </h4>
        {free.map((v) => (
          <div key={v.id} style={chipStyle}>
            {v.vehicle_type} ({v.id.slice(0, 6)})
          </div>
        ))}
      </div>
      <div>
        <h4 style={{ fontSize: 14, fontWeight: 600, color: "#f59e0b", marginBottom: 8 }}>
          Busy ({busy.length})
        </h4>
        {busy.map((v) => (
          <div key={v.id} style={{ ...chipStyle, borderColor: "#fde68a" }}>
            <div>
              {v.vehicle_type} ({v.id.slice(0, 6)})
            </div>
            {v.eta_return && (
              <div style={{ fontSize: 11, color: "#64748b" }}>
                ETA: {new Date(v.eta_return).toLocaleTimeString()}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

const chipStyle: React.CSSProperties = {
  padding: "6px 10px",
  border: "1px solid #bbf7d0",
  borderRadius: 8,
  marginBottom: 6,
  fontSize: 12,
  background: "#f0fdf4",
};
