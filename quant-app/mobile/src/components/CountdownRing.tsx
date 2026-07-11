import { View } from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import { colors } from '@/theme';
import { fmtClock } from '@/lib/format';
import { T } from './Text';

/**
 * CountdownRing (07 §2/§5.1): circular seconds_left, band-colored when in_window
 * (60–150s). Hero on the Live screen.
 */
export function CountdownRing({
  secondsLeft,
  cycleSec = 300,
  inWindow,
  marketSlug,
  size = 200,
  stroke = 14,
}: {
  secondsLeft: number;
  cycleSec?: number;
  inWindow: boolean;
  marketSlug?: string;
  size?: number;
  stroke?: number;
}) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const frac = Math.max(0, Math.min(1, secondsLeft / cycleSec));
  const dash = circumference * frac;
  const color = inWindow ? colors.accent.info : secondsLeft <= 20 ? colors.accent.down : colors.accent.up;

  return (
    <View style={{ alignItems: 'center', justifyContent: 'center' }}>
      <Svg width={size} height={size}>
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={colors.bg.elevated}
          strokeWidth={stroke}
          fill="none"
        />
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={color}
          strokeWidth={stroke}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circumference}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </Svg>
      <View style={{ position: 'absolute', alignItems: 'center' }}>
        <T variant="display" mono style={{ color }}>
          {fmtClock(secondsLeft)}
        </T>
        <T variant="caption" color="secondary">
          {inWindow ? 'in entry window' : 'until close'}
        </T>
        {marketSlug ? (
          <T variant="caption" color="muted" numberOfLines={1} style={{ maxWidth: size }}>
            {marketSlug}
          </T>
        ) : null}
      </View>
    </View>
  );
}
