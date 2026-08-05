/**
 * The address field, with completions.
 *
 * Typing shows a short dropdown of real addresses; choosing one fills the field and — because a
 * suggestion carries its own coordinates — lets the property be created even when the geocoder is
 * having a bad day. The field works exactly like a plain TextInput when suggestions are slow,
 * empty, or unavailable: they are an acceleration, never a gate.
 */

import { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { api } from '@/api/client';
import type { AddressSuggestion } from '@/api/types';
import { colors, radius, shadow, spacing, type } from '@/theme';

const DEBOUNCE_MS = 250;
const MIN_QUERY_LENGTH = 4;

export function AddressAutocomplete({
  value,
  onChangeText,
  onSelect,
  placeholder,
}: {
  value: string;
  onChangeText: (text: string) => void;
  /** Fired when the user picks a suggestion; the parent keeps the coordinates. */
  onSelect: (suggestion: AddressSuggestion) => void;
  placeholder?: string;
}) {
  const [suggestions, setSuggestions] = useState<AddressSuggestion[]>([]);
  const [open, setOpen] = useState(false);
  // Only the newest request may update the list: a slow answer to "123 M" must not replace the
  // answer to "123 Main St" the user has since typed.
  const requestSeq = useRef(0);
  const chosen = useRef<string | null>(null);

  useEffect(() => {
    const query = value.trim();
    // A bare ZIP gets its own treatment upstream, and a just-picked suggestion needs no dropdown.
    if (query.length < MIN_QUERY_LENGTH || /^\d{5}$/.test(query) || query === chosen.current) {
      setSuggestions([]);
      setOpen(false);
      return;
    }

    const seq = ++requestSeq.current;
    const timer = setTimeout(() => {
      api.suggestAddresses(query).then((results) => {
        if (seq !== requestSeq.current) return;
        setSuggestions(results);
        setOpen(results.length > 0);
      });
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [value]);

  function choose(suggestion: AddressSuggestion) {
    chosen.current = suggestion.label;
    setOpen(false);
    setSuggestions([]);
    onChangeText(suggestion.label);
    onSelect(suggestion);
  }

  return (
    <View style={styles.wrap}>
      <TextInput
        style={styles.input}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={colors.textMuted}
        autoCapitalize="words"
        autoCorrect={false}
        returnKeyType="next"
        onBlur={() => {
          // Give a tap on a suggestion time to land before the list disappears under it.
          setTimeout(() => setOpen(false), 150);
        }}
      />
      {open ? (
        <View style={styles.dropdown}>
          {suggestions.map((suggestion, index) => (
            <Pressable
              key={suggestion.label}
              onPress={() => choose(suggestion)}
              style={({ pressed }) => [
                styles.option,
                index > 0 && styles.optionDivider,
                pressed && styles.optionPressed,
              ]}
            >
              <Text style={styles.optionPin}>📍</Text>
              <Text style={styles.optionText} numberOfLines={1}>
                {suggestion.label}
              </Text>
            </Pressable>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { position: 'relative', zIndex: 10 },
  input: {
    ...type.body,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 6,
    marginTop: spacing.xs,
    backgroundColor: colors.surface,
    color: colors.text,
  },
  dropdown: {
    position: 'absolute',
    top: '100%',
    left: 0,
    right: 0,
    marginTop: spacing.xs,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    overflow: 'hidden',
    zIndex: 20,
    ...shadow.raised,
  },
  option: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 4,
  },
  optionDivider: {
    borderTopWidth: 1,
    borderTopColor: colors.surfaceMuted,
  },
  optionPressed: { backgroundColor: colors.accentMuted },
  optionPin: { fontSize: 13 },
  optionText: { ...type.body, flex: 1, color: colors.text },
});
