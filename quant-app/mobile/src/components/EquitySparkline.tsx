import { View } from 'react-native';
import Svg, { Path, Line } from 'react-native-svg';
import { colors } from '@/theme';
import { T } from './Text';
import type { EquityPoint } from '@/types';

/**
 * EquityChart / EquitySparkline (07 §2/§5.5): line of equity_curve[].cum_pnl over
 * time, with a zero baseline. Drawdown-from-peak shading kept light on dark theme.
 */
export function EquitySparkline({
  points,
  width = 320,
  height = 120,
  showZero = true,
}: {
  points: EquityPoint[];
  width?: number;
  height?: number;
  showZero?: boolean;
}) {
  if (points.length < 2) {
    return (
      <View style={{ height, justifyContent: 'center', alignItems: 'center' }}>
        <T variant="caption" color="muted">
          Equity curve builds as trades settle.
        </T>
      </View>
    );
  }

  const pad = 8;
  const xs = points.map((_, i) => i);
  const ys = points.map((p) => p.cum_pnl);
  const minY = Math.min(0, ...ys);
  const maxY = Math.max(0, ...ys);
  const spanY = maxY - minY || 1;
  const spanX = xs.length - 1 || 1;

  const px = (i: number) => pad + (i / spanX) * (width - pad * 2);
  const py = (v: number) => pad + (1 - (v - minY) / spanY) * (height - pad * 2);

  const d = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${px(i)} ${py(p.cum_pnl)}`).join(' ');
  const last = ys[ys.length - 1] ?? 0;
  const lineColor = last >= 0 ? colors.accent.up : colors.accent.down;
  const zeroY = py(0);

  // Area under the curve down to the zero baseline.
  const areaD = `${d} L ${px(spanX)} ${zeroY} L ${px(0)} ${zeroY} Z`;

  return (
    <Svg width={width} height={height}>
      {showZero && (
        <Line x1={pad} y1={zeroY} x2={width - pad} y2={zeroY} stroke={colors.border.subtle} strokeWidth={1} />
      )}
      <Path d={areaD} fill={lineColor} fillOpacity={0.12} />
      <Path d={d} stroke={lineColor} strokeWidth={2} fill="none" strokeLinejoin="round" />
    </Svg>
  );
}
