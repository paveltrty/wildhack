import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, Legend } from 'recharts';
import type { ForecastRow } from '../api/client';

interface Props {
  forecasts: ForecastRow[];
}

export default function ForecastChart({ forecasts }: Props) {
  const data = forecasts.map((f) => ({
    horizon: `h${f.horizon}`,
    y_hat_future: f.y_hat_future,
    y_hat_raw: f.y_hat_raw,
    confidence: f.confidence,
    y_hat_low: f.y_hat_low ?? 0,
    y_hat_high: f.y_hat_high ?? 0,
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
        <XAxis dataKey="horizon" tick={{ fill: '#8b949e', fontSize: 11 }} />
        <YAxis tick={{ fill: '#8b949e', fontSize: 11 }} />
        <Tooltip
          contentStyle={{
            background: '#1c2128',
            border: '1px solid #30363d',
            borderRadius: 6,
            color: '#e1e4e8',
          }}
        />
        <Legend />
        <Area
          type="monotone"
          dataKey="y_hat_high"
          stroke="none"
          fill="#58a6ff"
          fillOpacity={0.1}
          name="CI High"
        />
        <Area
          type="monotone"
          dataKey="y_hat_low"
          stroke="none"
          fill="#0d1117"
          fillOpacity={1}
          name="CI Low"
        />
        <Line type="monotone" dataKey="y_hat_future" stroke="#58a6ff" name="Forecast (future)" strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="y_hat_raw" stroke="#8b949e" name="Raw (2h)" strokeWidth={1} dot={false} strokeDasharray="4 2" />
      </LineChart>
    </ResponsiveContainer>
  );
}
