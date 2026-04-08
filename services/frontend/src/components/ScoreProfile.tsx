import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { ScoreDecision } from "../api/client";

interface Props {
  decisions: ScoreDecision[];
}

export default function ScoreProfile({ decisions }: Props) {
  const latest = decisions[0];
  if (!latest) return <p>No data</p>;

  const chartData = Object.entries(latest.scores_by_horizon)
    .map(([h, score]) => ({
      horizon: `h${h}`,
      score,
      isOptimal: parseInt(h) === latest.optimal_horizon,
    }))
    .sort((a, b) => parseInt(a.horizon.slice(1)) - parseInt(b.horizon.slice(1)));

  return (
    <div>
      <div style={{ fontSize: 13, color: "#64748b", marginBottom: 8 }}>
        Optimal: <strong>h{latest.optimal_horizon}</strong> (score: {latest.optimal_score.toFixed(3)})
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="horizon" tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} domain={[0, 1]} />
          <Tooltip
            contentStyle={{ borderRadius: 8, fontSize: 12 }}
            formatter={(value: number) => value.toFixed(3)}
          />
          <Bar dataKey="score" radius={[4, 4, 0, 0]}>
            {chartData.map((entry, idx) => (
              <Cell key={idx} fill={entry.isOptimal ? "#f59e0b" : "#93c5fd"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
