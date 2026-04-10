import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { api } from '../api/client';

interface Props {
  routeId: string;
  onClose: () => void;
}

const panelStyle: React.CSSProperties = {
  position: 'fixed',
  top: 0,
  right: 0,
  width: 420,
  height: '100vh',
  background: '#161b22',
  borderLeft: '1px solid #30363d',
  padding: '24px',
  overflowY: 'auto',
  zIndex: 200,
  boxShadow: '-4px 0 24px rgba(0,0,0,0.5)',
};

export default function RoutePanel({ routeId, onClose }: Props) {
  const navigate = useNavigate();

  const { data: forecasts } = useQuery({
    queryKey: ['forecasts', routeId],
    queryFn: () => api.getForecasts({ route_id: routeId }),
    refetchInterval: 30000,
  });

  const { data: orders } = useQuery({
    queryKey: ['orders', routeId],
    queryFn: () => api.getOrders({ route_id: routeId }),
    refetchInterval: 30000,
  });

  const { data: scoreProfiles } = useQuery({
    queryKey: ['scoreProfile', routeId],
    queryFn: () => api.getScoreProfile(routeId),
  });

  const latestProfile = scoreProfiles?.[0];
  const chosenHorizon = latestProfile?.chosen_horizon;

  const scoreData = forecasts
    ? Array.from({ length: 10 }, (_, i) => {
        const h = i + 1;
        const f = forecasts.find((r) => r.horizon === h);
        return {
          horizon: `h${h}`,
          y_hat_future: f?.y_hat_future ?? 0,
        };
      })
    : [];

  const statusColor = (status: string): string => {
    switch (status) {
      case 'draft': return '#8b949e';
      case 'approved': return '#58a6ff';
      case 'dispatched': return '#d29922';
      case 'completed': return '#3fb950';
      default: return '#6e7681';
    }
  };

  const officeFromId = orders?.[0]?.office_from_id ?? '';

  function goToOrders() {
    const qs = new URLSearchParams();
    if (officeFromId) qs.set('office_from_id', officeFromId);
    qs.set('route_id', routeId);
    navigate(`/orders?${qs}`);
  }

  return (
    <div style={panelStyle}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, color: '#e1e4e8' }}>Route: {routeId}</h2>
        <button
          onClick={onClose}
          style={{
            background: 'none',
            border: '1px solid #30363d',
            color: '#8b949e',
            borderRadius: 6,
            padding: '4px 12px',
            cursor: 'pointer',
            fontSize: 14,
          }}
        >
          Close
        </button>
      </div>

      <div style={{ marginBottom: 24 }}>
        <h3 style={{ fontSize: 14, color: '#8b949e', marginBottom: 12 }}>Score Profile (Horizons 1-10)</h3>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={scoreData}>
            <XAxis dataKey="horizon" tick={{ fill: '#8b949e', fontSize: 11 }} />
            <YAxis tick={{ fill: '#8b949e', fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: '#1c2128', border: '1px solid #30363d', borderRadius: 6, color: '#e1e4e8' }}
            />
            <Bar dataKey="y_hat_future" name="Forecast">
              {scoreData.map((_, idx) => (
                <Cell
                  key={idx}
                  fill={idx + 1 === chosenHorizon ? '#d29922' : '#58a6ff'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h3 style={{ fontSize: 14, color: '#8b949e', margin: 0 }}>Orders</h3>
          {orders && orders.length > 0 && (
            <button
              onClick={goToOrders}
              style={{
                background: 'transparent',
                border: '1px solid #30363d',
                color: '#58a6ff',
                borderRadius: 6,
                padding: '3px 10px',
                cursor: 'pointer',
                fontSize: 11,
                fontWeight: 600,
                transition: 'all 0.15s',
              }}
            >
              Открыть все в Заявках &rarr;
            </button>
          )}
        </div>
        {orders && orders.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {orders.map((o) => (
              <div
                key={o.id}
                onClick={() => {
                  const qs = new URLSearchParams();
                  qs.set('office_from_id', o.office_from_id);
                  qs.set('route_id', o.route_id);
                  navigate(`/orders?${qs}`);
                }}
                style={{
                  padding: '10px 14px',
                  background: '#0d1117',
                  borderRadius: 8,
                  border: '1px solid #21262d',
                  fontSize: 12,
                  cursor: 'pointer',
                  transition: 'border-color 0.15s',
                }}
                onMouseEnter={(e) =>
                  (e.currentTarget.style.borderColor = '#58a6ff')
                }
                onMouseLeave={(e) =>
                  (e.currentTarget.style.borderColor = '#21262d')
                }
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ color: '#e1e4e8', fontWeight: 600 }}>
                    h{o.chosen_horizon} &middot; {o.vehicle_count} {o.vehicle_type}
                  </span>
                  <span
                    style={{
                      color: statusColor(o.status),
                      fontWeight: 600,
                      textTransform: 'uppercase',
                      fontSize: 10,
                      padding: '2px 8px',
                      borderRadius: 10,
                      border: `1px solid ${statusColor(o.status)}`,
                    }}
                  >
                    {o.status}
                  </span>
                </div>
                <div style={{ color: '#8b949e' }}>
                  Departure: {new Date(o.scheduled_departure).toLocaleString()}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: '#8b949e' }}>
                    Score: {o.optimizer_score.toFixed(3)} &middot; Forecast: {o.y_hat_future.toFixed(1)}
                  </span>
                  <span style={{ color: '#58a6ff', fontSize: 10, fontWeight: 600 }}>
                    Открыть &rarr;
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ color: '#6e7681', fontSize: 13 }}>No orders for this route.</div>
        )}
      </div>
    </div>
  );
}
