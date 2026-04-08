import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, ComposedChart } from "recharts";
import { Forecast } from "../api/client";

interface Props {
  forecasts: Forecast[];
}

export default function ForecastChart({ forecasts }: Props) {
  const chartData = forecasts.map((f) => ({
    horizon: `h${f.horizon}`,
    y_hat: f.y_hat,
    y_hat_low: f.y_hat_low ?? f.y_hat * 0.8,
    y_hat_high: f.y_hat_high ?? f.y_hat * 1.2,
    confidence: f.confidence,
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey="horizon" tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} />
        <Tooltip
          contentStyle={{ borderRadius: 8, fontSize: 12 }}
          formatter={(value: number) => value.toFixed(2)}
        />
        <Area
          dataKey="y_hat_high"
          stroke="none"
          fill="#bfdbfe"
          fillOpacity={0.4}
          name="Upper bound"
        />
        <Area
          dataKey="y_hat_low"
          stroke="none"
          fill="#fff"
          fillOpacity={1}
          name="Lower bound"
        />
        <Line
          dataKey="y_hat"
          stroke="#3b82f6"
          strokeWidth={2}
          dot={{ fill: "#3b82f6", r: 4 }}
          name="Forecast"
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
