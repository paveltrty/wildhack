import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  Line,
  ComposedChart,
  Legend,
} from 'recharts';

interface ScoreData {
  horizon: string;
  y_hat_future: number;
  confidence: number;
  isChosen: boolean;
}

interface Props {
  data: ScoreData[];
}

export default function ScoreProfile({ data }: Props) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
        <XAxis dataKey="horizon" tick={{ fill: '#8b949e', fontSize: 11 }} />
        <YAxis yAxisId="left" tick={{ fill: '#8b949e', fontSize: 11 }} />
        <YAxis yAxisId="right" orientation="right" tick={{ fill: '#8b949e', fontSize: 11 }} domain={[0, 1]} />
        <Tooltip
          contentStyle={{
            background: '#1c2128',
            border: '1px solid #30363d',
            borderRadius: 6,
            color: '#e1e4e8',
          }}
        />
        <Legend />
        <Bar yAxisId="left" dataKey="y_hat_future" name="Score" barSize={24}>
          {data.map((entry, idx) => (
            <Cell key={idx} fill={entry.isChosen ? '#d29922' : '#58a6ff'} />
          ))}
        </Bar>
        <Line
          yAxisId="right"
          type="monotone"
          dataKey="confidence"
          stroke="#3fb950"
          name="Confidence"
          dot={false}
          strokeWidth={2}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
