/**
 * The ambient background: two soft color fields drifting very slowly behind a screen.
 *
 * The motion is glacial on purpose — a full drift takes most of a minute — so it reads as light
 * moving across a room, not as an animation asking to be watched. Colors come from the brand's
 * two halves (ember warmth, water cool) at whisper opacity over the warm paper, which is what
 * keeps text contrast untouched.
 */

import { LinearGradient } from 'expo-linear-gradient';
import { useEffect, useRef } from 'react';
import { Animated, Easing, StyleSheet } from 'react-native';

function useDrift(duration: number) {
  const value = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(value, {
          toValue: 1,
          duration,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
        Animated.timing(value, {
          toValue: 0,
          duration,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [value, duration]);
  return value;
}

export function AmbientBackground() {
  const warm = useDrift(42000);
  const cool = useDrift(56000);

  return (
    <>
      <Animated.View
        pointerEvents="none"
        style={[
          styles.blob,
          styles.warm,
          {
            transform: [
              { translateX: warm.interpolate({ inputRange: [0, 1], outputRange: [-40, 60] }) },
              { translateY: warm.interpolate({ inputRange: [0, 1], outputRange: [0, 90] }) },
              { scale: warm.interpolate({ inputRange: [0, 1], outputRange: [1, 1.25] }) },
            ],
          },
        ]}
      >
        <LinearGradient
          colors={['rgba(199, 91, 57, 0.10)', 'rgba(199, 91, 57, 0)']}
          style={styles.fill}
        />
      </Animated.View>
      <Animated.View
        pointerEvents="none"
        style={[
          styles.blob,
          styles.cool,
          {
            transform: [
              { translateX: cool.interpolate({ inputRange: [0, 1], outputRange: [50, -70] }) },
              { translateY: cool.interpolate({ inputRange: [0, 1], outputRange: [40, -50] }) },
              { scale: cool.interpolate({ inputRange: [0, 1], outputRange: [1.15, 0.95] }) },
            ],
          },
        ]}
      >
        <LinearGradient
          colors={['rgba(31, 98, 115, 0.09)', 'rgba(31, 98, 115, 0)']}
          style={styles.fill}
        />
      </Animated.View>
    </>
  );
}

const styles = StyleSheet.create({
  blob: {
    position: 'absolute',
    width: 480,
    height: 480,
    borderRadius: 240,
    overflow: 'hidden',
  },
  warm: { top: -140, right: -160 },
  cool: { bottom: -180, left: -180 },
  fill: { flex: 1, borderRadius: 240 },
});
