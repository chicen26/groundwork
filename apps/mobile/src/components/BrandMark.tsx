/**
 * The mark: a flame holding a water droplet.
 *
 * The whole product in one shape — the fire risk outside, the water answer inside, drawn soft
 * enough to feel like a garden brand rather than a warning sign. Vector, so the same component is
 * the tiny wordmark companion, the hero watermark, and the favicon source.
 */

import Svg, { Path } from 'react-native-svg';

import { colors } from '@/theme';

export function BrandMark({
  size = 24,
  flame = colors.emberBright,
  drop = colors.waterBright,
}: {
  size?: number;
  flame?: string;
  drop?: string;
}) {
  return (
    <Svg width={size} height={size} viewBox="0 0 64 64" fill="none">
      {/* Flame: leans right as if in wind, like a real one. */}
      <Path
        d="M33 4
           C 30 14, 18 20, 15 32
           C 12.5 43, 19 56, 32 58
           C 45 56, 51.5 44, 49 33
           C 47.5 26.5, 43 22, 41 16
           C 43.5 24, 40 27, 38.5 27.5
           C 41 18, 37 9, 33 4 Z"
        fill={flame}
      />
      {/* The droplet it carries. */}
      <Path
        d="M32 30
           C 34.5 34.5, 40 37.5, 40 43.5
           A 8 8 0 1 1 24 43.5
           C 24 37.5, 29.5 34.5, 32 30 Z"
        fill={drop}
      />
    </Svg>
  );
}
