import { useMemo } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { CHART, METHOD_LABEL, limitColor, seriesColor } from "@/theme/chart";
import type { SeriesPoint } from "@/shared/types";

type Props = {
  series: SeriesPoint[];
  unit: string | null;
  lowerLimit: number | null;
  upperLimit: number | null;
  parameter: string;
};

/**
 * Measurement history against the governing band.
 *
 * One measure, one axis. Field and lab are separate series rather than a
 * pooled average because they disagree materially -- on SYS-0006 the lab reads
 * a third of the field value on the same equipment -- and averaging them
 * flattens the trend this chart exists to show.
 *
 * The action level is drawn as a reference line, not a series, in a reserved
 * status colour. On the corrosion case it is the whole point: the line climbs
 * for six months and never reaches the threshold.
 */
export function TrendChart({ series, unit, lowerLimit, upperLimit, parameter }: Props) {
  const theme = useTheme();
  const mode = theme.palette.mode;

  const { methods, data } = useMemo(() => {
    const present = Array.from(new Set(series.map((p) => p.collection_method)));
    const byTime = new Map<number, Record<string, number | string>>();
    for (const point of series) {
      const key = new Date(point.observed_at).getTime();
      const row = byTime.get(key) ?? { t: key };
      row[point.collection_method] = point.value;
      byTime.set(key, row);
    }
    return {
      methods: present,
      data: Array.from(byTime.values()).sort((a, b) => Number(a.t) - Number(b.t)),
    };
  }, [series]);

  if (series.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        No measurement history for this parameter.
      </Typography>
    );
  }

  const axisTick = { fill: theme.palette.text.secondary, fontSize: 12 };
  const limit = limitColor(mode);

  return (
    <Box>
      <Stack
        direction="row"
        justifyContent="space-between"
        alignItems="baseline"
        sx={{ mb: 1 }}
      >
        <Typography variant="subtitle2">
          {parameter.replace(/_/g, " ")} history
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {unit ?? ""} · {series.length} observations
        </Typography>
      </Stack>

      <Box sx={{ width: "100%", height: 300 }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid
              stroke={theme.palette.divider}
              strokeOpacity={CHART.gridOpacity}
              vertical={false}
            />
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={["dataMin", "dataMax"]}
              tick={axisTick}
              tickLine={false}
              axisLine={{ stroke: theme.palette.divider }}
              tickFormatter={(value) =>
                new Date(value).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                })
              }
            />
            <YAxis
              tick={axisTick}
              tickLine={false}
              axisLine={false}
              width={56}
              label={{
                value: unit ?? "",
                angle: -90,
                position: "insideLeft",
                style: { fill: theme.palette.text.secondary, fontSize: 11 },
              }}
            />
            <Tooltip
              contentStyle={{
                background: theme.palette.background.paper,
                border: `1px solid ${theme.palette.divider}`,
                borderRadius: 8,
                fontSize: 12,
              }}
              labelFormatter={(value) =>
                new Date(Number(value)).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                })
              }
              formatter={(value, name) => [
                `${value} ${unit ?? ""}`,
                METHOD_LABEL[String(name)] ?? String(name),
              ]}
            />
            <Legend
              formatter={(value) => (
                <span style={{ color: theme.palette.text.secondary, fontSize: 12 }}>
                  {METHOD_LABEL[String(value)] ?? String(value)}
                </span>
              )}
            />

            {upperLimit != null && (
              <ReferenceLine
                y={upperLimit}
                stroke={limit}
                strokeDasharray="6 4"
                strokeWidth={1.5}
                label={{
                  value: `Action level ${upperLimit} ${unit ?? ""}`,
                  position: "insideTopRight",
                  style: { fill: limit, fontSize: 11, fontWeight: 600 },
                }}
              />
            )}
            {lowerLimit != null && (
              <ReferenceLine
                y={lowerLimit}
                stroke={limit}
                strokeDasharray="6 4"
                strokeWidth={1.5}
                label={{
                  value: `Lower limit ${lowerLimit} ${unit ?? ""}`,
                  position: "insideBottomRight",
                  style: { fill: limit, fontSize: 11, fontWeight: 600 },
                }}
              />
            )}

            {methods.map((method) => (
              <Line
                key={method}
                type="monotone"
                dataKey={method}
                name={method}
                stroke={seriesColor(mode, method)}
                strokeWidth={CHART.strokeWidth}
                dot={{ r: 3, strokeWidth: 0, fill: seriesColor(mode, method) }}
                activeDot={{
                  r: CHART.markerSize / 2,
                  strokeWidth: 2,
                  stroke: theme.palette.background.paper,
                }}
                connectNulls
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </Box>
    </Box>
  );
}
