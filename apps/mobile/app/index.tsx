/**
 * Home: the properties you have added, or the way in if you have not.
 *
 * The welcome screen is the shop window: a dark evergreen hero in the brand serif, and a ZIP
 * field that gives a visitor a real (honestly-approximate) answer before any sign-up. Sign-in
 * stays a single tap while Supabase auth is unconfigured: asking a homeowner to create an account
 * before they have seen the product would cost more testers than it protects.
 */

import { LinearGradient } from 'expo-linear-gradient';
import { Link, Stack, useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Animated,
  FlatList,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { api } from '@/api/client';
import type { FhszClass, ImpactStats, Property } from '@/api/types';
import { BrandMark } from '@/components/BrandMark';
import { PrivacyNote } from '@/components/PrivacyNote';
import { Button, Card, ErrorNote, Loading, Screen, ZoneBadge } from '@/components/ui';
import { ZipQuickLookCard, useZipQuickLook } from '@/components/ZipQuickLook';
import { useT } from '@/i18n';
import { newUserId, useSession } from '@/session';
import { colors, fonts, radius, shadow, spacing, type } from '@/theme';
import { currentSeason } from '@/theme/season';

export default function HomeScreen() {
  const { credentials, loading: sessionLoading, signIn, accountsEnabled } = useSession();
  const router = useRouter();
  const [properties, setProperties] = useState<Property[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(() => {
    if (!credentials) return;
    setError(null);
    api
      .listProperties(credentials)
      .then(setProperties)
      .catch((e: Error) => setError(e.message))
      .finally(() => setRefreshing(false));
  }, [credentials]);

  // Reload on focus: coming back from a finished scan should show the new state, not a stale list.
  useFocusEffect(load);

  const t = useT();

  if (sessionLoading) return <Loading />;

  if (!credentials) {
    // With accounts configured, the way in is a real sign-in; without them, one tap starts a
    // device-local session — a gate with nothing behind it would just cost testers.
    return (
      <Welcome onStart={() => (accountsEnabled ? router.push('/signin') : signIn(newUserId()))} />
    );
  }

  if (error) {
    return (
      <Screen style={styles.padded}>
        <ErrorNote message={error} onRetry={load} />
      </Screen>
    );
  }

  if (!properties) return <Loading label={t('Loading your properties')} />;

  return (
    <Screen>
      <Stack.Screen
        options={{
          headerRight: () => (
            <Pressable onPress={() => router.push('/settings')} hitSlop={12}>
              <Text style={styles.gear}>⚙︎</Text>
            </Pressable>
          ),
        }}
      />
      <FlatList
        contentContainerStyle={styles.list}
        data={properties}
        keyExtractor={(item) => item.id}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => {
              setRefreshing(true);
              load();
            }}
            tintColor={colors.accent}
          />
        }
        ListHeaderComponent={
          properties.length > 0 ? (
            <Text style={[type.overline, styles.listOverline]}>{t('Your properties')}</Text>
          ) : null
        }
        ListEmptyComponent={
          <Card>
            <Text style={type.heading}>{t('No properties yet')}</Text>
            <Text style={styles.body}>
              {t(
                'Add your address and we will look up its fire hazard zone, then walk you through photographing the yard.',
              )}
            </Text>
          </Card>
        }
        ListFooterComponent={
          <Link href="/properties/new" asChild>
            <Button title={t('Add a property')} onPress={() => router.push('/properties/new')} />
          </Link>
        }
        renderItem={({ item }) => (
          <Pressable onPress={() => router.push(`/properties/${item.id}`)}>
            {({ pressed }) => (
              <Card style={pressed ? styles.cardPressed : undefined}>
                <View style={styles.cardRow}>
                  <View style={[styles.cardRail, { backgroundColor: railColor(item.geo.fhsz) }]} />
                  <View style={styles.cardBody}>
                    <Text style={type.heading}>{item.label ?? item.address}</Text>
                    {item.label ? <Text style={styles.body}>{item.address}</Text> : null}
                    <View style={styles.badgeRow}>
                      <ZoneBadge fhsz={item.geo.fhsz} />
                    </View>
                  </View>
                  <Text style={styles.chevron}>›</Text>
                </View>
              </Card>
            )}
          </Pressable>
        )}
      />
    </Screen>
  );
}

function railColor(fhsz: FhszClass): string {
  switch (fhsz) {
    case 'very_high':
      return colors.critical;
    case 'high':
      return colors.high;
    case 'moderate':
      return colors.moderate;
    case 'non_wildland':
      return colors.low;
    default:
      return colors.border;
  }
}

function Welcome({ onStart }: { onStart: () => void }) {
  const t = useT();
  const [zipInput, setZipInput] = useState('');
  const [zip, setZip] = useState<string | null>(null);
  const quickLook = useZipQuickLook(zip);
  const canPeek = /^\d{5}$/.test(zipInput.trim());

  const [impact, setImpact] = useState<ImpactStats | null>(null);
  useEffect(() => {
    api.impactStats().then(setImpact);
  }, []);

  // The hero settles into place on arrival — one soft movement, then stillness.
  const entrance = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.timing(entrance, { toValue: 1, duration: 600, useNativeDriver: true }).start();
  }, [entrance]);
  const settle = {
    opacity: entrance,
    transform: [{ translateY: entrance.interpolate({ inputRange: [0, 1], outputRange: [14, 0] }) }],
  };

  const season = currentSeason();

  return (
    <Screen>
      {/* The hero carries the wordmark itself; a header saying it again would just repeat it. */}
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.welcomeScroll}>
        <LinearGradient
          colors={season.heroColors}
          start={{ x: 0.1, y: 0 }}
          end={{ x: 0.9, y: 1 }}
          style={styles.hero}
        >
          {/* The mark, huge and barely-there, growing out of the corner like the thing it names. */}
          <View style={styles.heroWatermark}>
            <BrandMark size={340} flame="rgba(245, 241, 230, 0.05)" drop="rgba(245,241,230,0.07)" />
          </View>
          <Animated.View style={[styles.heroInner, settle]}>
            <View style={styles.brandRow}>
              <BrandMark size={30} />
              <Text style={styles.brandName}>Groundwork</Text>
            </View>

            <Text style={styles.heroTitle}>
              <Text style={styles.heroEmber}>{t('Fire-safe.')}</Text>{' '}
              <Text style={styles.heroWater}>{t('Water-wise.')}</Text>
              {'\n'}
              <Text style={styles.heroCream}>{t('One plan for your yard.')}</Text>
            </Text>

            <Text style={styles.heroTagline}>
              {t(
                'Scan your yard once. Get one ranked plan that satisfies wildfire rules and water-saving rebates, with the programs that pay for it.',
              )}
            </Text>

            <View style={styles.chipRow}>
              <HeroChip icon="🔥" label={t('Defensible space')} />
              <HeroChip icon="💧" label={t('Lawn rebates')} />
              <HeroChip icon="🧾" label={t('One ranked plan')} />
            </View>

            {season.badge ? (
              <View style={styles.seasonBadge}>
                <Text style={styles.seasonBadgeText}>{t(season.badge)}</Text>
              </View>
            ) : null}
          </Animated.View>
        </LinearGradient>

        <View style={styles.welcomeBody}>
          {/* The ZIP card straddles the hero's edge: the first thing your eye lands on is the
              thing you can actually do. */}
          <View style={styles.zipCard}>
            <Text style={type.overline}>{t('Curious? Start with just your ZIP')}</Text>
            <View style={styles.zipRow}>
              <TextInput
                style={styles.zipInput}
                value={zipInput}
                onChangeText={setZipInput}
                placeholder="94526"
                placeholderTextColor={colors.textMuted}
                keyboardType="number-pad"
                maxLength={5}
                onSubmitEditing={() => canPeek && setZip(zipInput.trim())}
              />
              <Button
                title={quickLook.loading ? t('Looking…') : t('Take a look')}
                variant="secondary"
                onPress={() => setZip(zipInput.trim())}
                disabled={!canPeek || quickLook.loading}
              />
            </View>
            {quickLook.error ? <Text style={styles.zipError}>{quickLook.error}</Text> : null}
          </View>

          {quickLook.result ? (
            <ZipQuickLookCard
              look={quickLook.result}
              ctaHint={t('Get started below with your full address')}
            />
          ) : null}

          <View style={styles.steps}>
            <Step
              n="1"
              title={t('Walk your yard')}
              text={t('Seven photos, guided. Or answer a two-minute checklist, no camera needed.')}
            />
            <Step
              n="2"
              title={t('See what matters')}
              text={t(
                'Hazards ranked against the actual rules for your zone, each with its citation.',
              )}
            />
            <Step
              n="3"
              title={t('Get paid to fix it')}
              text={t(
                'Lawn-replacement rebates from your own water utility, calculated for your yard.',
              )}
            />
          </View>

          {impact && impact.assessments > 0 ? (
            <View style={styles.impactBand}>
              <Text style={[type.overline, styles.impactTitle]}>
                {t('So far, with our testers')}
              </Text>
              <View style={styles.impactRow}>
                <Text style={styles.impactStat}>
                  {t('{n} yards assessed', { n: impact.assessments.toLocaleString() })}
                </Text>
                {impact.plan_items_done > 0 ? (
                  <Text style={styles.impactStat}>
                    {t('{n} tasks completed', { n: impact.plan_items_done.toLocaleString() })}
                  </Text>
                ) : null}
                {impact.rebate_dollars_identified > 0 ? (
                  <Text style={styles.impactStat}>
                    {t('${n} in rebates identified', {
                      n: impact.rebate_dollars_identified.toLocaleString(),
                    })}
                  </Text>
                ) : null}
                {impact.annual_gallons_saved > 0 ? (
                  <Text style={styles.impactStat}>
                    {t('{n} gallons/yr in savings mapped', {
                      n: impact.annual_gallons_saved.toLocaleString(),
                    })}
                  </Text>
                ) : null}
              </View>
            </View>
          ) : null}

          <Button title={t('Get started')} onPress={onStart} />
          <PrivacyNote />
          <Text style={styles.fineprint}>
            {t(
              'Groundwork gives educational guidance based on published state and local requirements. It is not an official inspection and does not provide evacuation advice.',
            )}
          </Text>
        </View>
      </ScrollView>
    </Screen>
  );
}

function HeroChip({ icon, label }: { icon: string; label: string }) {
  return (
    <View style={styles.chip}>
      <Text style={styles.chipIcon}>{icon}</Text>
      <Text style={styles.chipLabel}>{label}</Text>
    </View>
  );
}

function Step({ n, title, text }: { n: string; title: string; text: string }) {
  return (
    <View style={styles.step}>
      <View style={styles.stepBadge}>
        <Text style={styles.stepNumber}>{n}</Text>
      </View>
      <View style={styles.stepBody}>
        <Text style={type.heading}>{title}</Text>
        <Text style={styles.stepText}>{text}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  welcomeScroll: { paddingBottom: spacing.xl },
  hero: {
    borderBottomLeftRadius: radius.lg + 8,
    borderBottomRightRadius: radius.lg + 8,
    overflow: 'hidden',
  },
  heroInner: {
    padding: spacing.lg,
    paddingTop: spacing.xxl + spacing.md,
    // Room for the ZIP card that overlaps the hero's bottom edge.
    paddingBottom: spacing.xxl + spacing.lg,
    gap: spacing.lg,
    maxWidth: 680,
    width: '100%',
    alignSelf: 'center',
  },
  heroWatermark: {
    position: 'absolute',
    right: -70,
    bottom: -60,
    transform: [{ rotate: '-8deg' }],
    pointerEvents: 'none',
  },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  brandName: {
    fontFamily: fonts.displayBold,
    fontSize: 20,
    color: colors.cream,
    letterSpacing: 0.3,
  },
  heroTitle: { ...type.display, fontFamily: fonts.displayBlack, color: colors.cream },
  heroCream: { color: colors.cream },
  heroEmber: { color: colors.emberBright },
  heroWater: { color: colors.waterBright },
  heroTagline: { ...type.body, color: colors.creamMuted, fontSize: 17, lineHeight: 26 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: colors.creamFaint,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  chipIcon: { fontSize: 13 },
  chipLabel: { ...type.label, color: colors.cream, fontSize: 13 },
  seasonBadge: {
    alignSelf: 'flex-start',
    backgroundColor: 'rgba(226, 121, 78, 0.16)',
    borderWidth: 1,
    borderColor: 'rgba(226, 121, 78, 0.45)',
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
  },
  seasonBadgeText: { ...type.caption, color: colors.emberBright, fontWeight: '600' },
  welcomeBody: {
    padding: spacing.lg,
    paddingTop: 0,
    marginTop: -spacing.xl - spacing.sm,
    gap: spacing.lg,
    maxWidth: 680,
    width: '100%',
    alignSelf: 'center',
  },
  zipCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.md + 4,
    gap: spacing.sm,
    ...shadow.raised,
  },
  zipRow: { gap: spacing.sm, alignItems: 'stretch' },
  zipInput: {
    ...type.title,
    letterSpacing: 6,
    textAlign: 'center',
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    backgroundColor: colors.background,
    color: colors.text,
  },
  zipError: { ...type.caption, color: colors.critical },
  steps: { gap: spacing.md, marginVertical: spacing.sm },
  step: { flexDirection: 'row', gap: spacing.md, alignItems: 'flex-start' },
  stepBadge: {
    width: 34,
    height: 34,
    borderRadius: radius.pill,
    backgroundColor: colors.accentMuted,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 2,
  },
  stepNumber: { fontFamily: fonts.displayBold, fontSize: 16, color: colors.accent },
  stepBody: { flex: 1, gap: 2 },
  stepText: { ...type.body, fontSize: 15, lineHeight: 21, color: colors.textMuted },
  fineprint: { ...type.caption, color: colors.textMuted },
  impactBand: {
    backgroundColor: colors.accentMuted,
    borderRadius: radius.lg,
    padding: spacing.md + 2,
    gap: spacing.sm,
  },
  impactTitle: { color: colors.accent },
  impactRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, rowGap: spacing.xs },
  impactStat: { ...type.label, color: colors.accent },
  padded: { padding: spacing.lg },
  list: { padding: spacing.lg, maxWidth: 720, width: '100%', alignSelf: 'center' },
  listOverline: { color: colors.textMuted, marginBottom: spacing.md },
  body: { ...type.body, color: colors.textMuted, marginTop: spacing.xs },
  badgeRow: { marginTop: spacing.sm, flexDirection: 'row' },
  cardRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  cardRail: {
    alignSelf: 'stretch',
    width: 4,
    borderRadius: 2,
  },
  cardBody: { flex: 1 },
  cardPressed: { opacity: 0.9 },
  chevron: { fontSize: 28, color: colors.textMuted, fontWeight: '300' },
  gear: { fontSize: 22, color: colors.text },
});
