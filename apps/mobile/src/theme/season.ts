/**
 * Season awareness, lightly.
 *
 * California's fire season is a real thing homeowners track, so the app may as well know what
 * month it is: a warmer hero and a small badge June through October, a cooler, calmer cast the
 * rest of the year. Cosmetic only — nothing about scores, rules, or alerts ever depends on this;
 * live warnings come from the NWS feed, not the calendar.
 */

import { colors } from './index';

export interface Season {
  key: 'fire' | 'green';
  /** Small badge text for the hero, or null when there is nothing worth saying. */
  badge: string | null;
  /** Hero gradient, tilted warm in fire season and cool-green outside it. */
  heroColors: [string, string];
}

export function currentSeason(now: Date = new Date()): Season {
  const month = now.getMonth() + 1;
  if (month >= 6 && month <= 10) {
    return {
      key: 'fire',
      badge: '🔥 Fire season: a good month to clear defensible space',
      heroColors: ['#1F1A0C', '#3A3018'],
    };
  }
  return {
    key: 'green',
    badge: null,
    heroColors: [colors.heroTop, colors.heroBottom],
  };
}
