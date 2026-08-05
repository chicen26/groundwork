/**
 * Two languages, one dictionary.
 *
 * Keys are the English strings themselves: the code stays readable, a missing translation falls
 * back to English instead of a blank, and adding a language is one more map. Content that carries
 * legal weight — citations, statute names, the rulebook's own text — stays in its original
 * language on purpose: a translated citation is a claim we cannot stand behind.
 *
 * Spanish is first because CA-10 speaks it: an app about protecting homes should speak to the
 * people living in them.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

export type Locale = 'en' | 'es';

const STORAGE_KEY = 'groundwork.locale';

function deviceLocale(): Locale {
  try {
    const tag =
      (typeof navigator !== 'undefined' && navigator.language) ||
      Intl.DateTimeFormat().resolvedOptions().locale ||
      'en';
    return tag.toLowerCase().startsWith('es') ? 'es' : 'en';
  } catch {
    return 'en';
  }
}

interface LocaleValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
}

const LocaleContext = createContext<LocaleValue>({ locale: 'en', setLocale: () => {} });

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>('en');

  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY)
      .then((stored) =>
        setLocaleState(stored === 'es' || stored === 'en' ? stored : deviceLocale()),
      )
      .catch(() => setLocaleState(deviceLocale()));
  }, []);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    AsyncStorage.setItem(STORAGE_KEY, next).catch(() => {});
  }, []);

  const value = useMemo(() => ({ locale, setLocale }), [locale, setLocale]);
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale(): LocaleValue {
  return useContext(LocaleContext);
}

/** The translator. `t('Add a property')`, or with variables: `t('{n} of {total}', {n: 3, ...})`. */
export function useT() {
  const { locale } = useLocale();
  return useCallback(
    (text: string, vars?: Record<string, string | number>) => {
      let out = locale === 'es' ? (ES[text] ?? text) : text;
      if (vars) {
        for (const [key, value] of Object.entries(vars)) {
          out = out.replaceAll(`{${key}}`, String(value));
        }
      }
      return out;
    },
    [locale],
  );
}

/** Spanish prompts for the guided checklist, keyed by question id so server text stays canonical. */
export const CHECKLIST_ES: Record<string, { prompt: string; help: string }> = {
  dead_vegetation_present: {
    prompt: '¿Hay vegetación muerta o seca a menos de 30 pies de la casa?',
    help: 'Arbustos muertos, pasto seco, hojas caídas o ramas muertas todavía en la planta.',
  },
  roof_debris_present: {
    prompt: '¿Hay hojas o agujas de pino acumuladas sobre el techo?',
    help: 'Revisa los valles del techo y donde el techo se une con una pared; ahí se acumulan.',
  },
  gutters_full: {
    prompt: '¿Las canaletas tienen hojas o desechos?',
    help: 'Las agujas y hojas en una canaleta sostienen el fuego justo contra el borde del techo.',
  },
  limbs_near_chimney: {
    prompt: '¿Alguna rama está a menos de 10 pies de la chimenea o del tubo de escape?',
    help: 'Mide desde la salida, no desde la superficie del techo.',
  },
  vents_unscreened: {
    prompt:
      '¿Alguna rejilla del ático o del sótano está sin malla, o con malla de más de 1/8 de pulgada?',
    help: 'Las brasas que entran por una rejilla abierta inician un fuego dentro de las paredes, fuera de la vista.',
  },
  vegetation_against_walls: {
    prompt: '¿Hay algo plantado o creciendo contra las paredes exteriores?',
    help: 'Arbustos, enredaderas o setos que tocan el revestimiento.',
  },
  combustible_mulch_present: {
    prompt: '¿Hay mantillo de corteza o madera en los primeros cinco pies alrededor de la casa?',
    help: 'La grava, la piedra y la tierra desnuda están bien; nos referimos a la corteza triturada.',
  },
  wood_fence_attached: {
    prompt: '¿Alguna cerca o portón de madera se conecta directamente con la casa?',
    help: 'Una cerca que toca la pared lleva el fuego directo a la estructura.',
  },
  storage_under_deck: {
    prompt: '¿Hay algo guardado debajo de una terraza o porche?',
    help: 'Leña, muebles, contenedores: cualquier cosa que arda sin ser vista.',
  },
  firewood_near_house: {
    prompt: '¿Hay leña o madera apilada a menos de 30 pies de la casa?',
    help: 'Incluye pilas contra una cerca o cobertizo que toque la casa.',
  },
  outer_zone_fuels_dense: {
    prompt: 'Entre 30 y 100 pies de la casa, ¿los arbustos y árboles crecen unos sobre otros?',
    help: 'El combustible continuo deja que el fuego suba del suelo a las copas de los árboles.',
  },
  grass_over_four_inches: {
    prompt: '¿Hay pasto de más de cuatro pulgadas en la propiedad?',
    help: 'Los pastos anuales se secan y propagan el fuego rápidamente.',
  },
};

/** English text → Spanish. Missing keys render in English rather than breaking. */
const ES: Record<string, string> = {
  // Brand / hero
  'Fire-safe.': 'A salvo del fuego.',
  'Water-wise.': 'Con agua sensata.',
  'One plan for your yard.': 'Un solo plan para tu jardín.',
  'Scan your yard once. Get one ranked plan that satisfies wildfire rules and water-saving rebates, with the programs that pay for it.':
    'Escanea tu jardín una vez. Recibe un plan ordenado que cumple las reglas contra incendios y los reembolsos por ahorrar agua, con los programas que lo pagan.',
  'Defensible space': 'Espacio defendible',
  'Lawn rebates': 'Reembolsos de césped',
  'One ranked plan': 'Un plan ordenado',
  '🔥 Fire season: a good month to clear defensible space':
    '🔥 Temporada de incendios: buen mes para despejar tu espacio defendible',
  'Curious? Start with just your ZIP': '¿Curiosidad? Empieza solo con tu código postal',
  'Take a look': 'Echar un vistazo',
  'Looking…': 'Buscando…',
  'Get started': 'Comenzar',
  'Walk your yard': 'Recorre tu jardín',
  'Seven photos, guided. Or answer a two-minute checklist, no camera needed.':
    'Siete fotos guiadas. O responde una lista de dos minutos, sin cámara.',
  'See what matters': 'Mira lo que importa',
  'Hazards ranked against the actual rules for your zone, each with its citation.':
    'Riesgos ordenados según las reglas reales de tu zona, cada uno con su cita legal.',
  'Get paid to fix it': 'Recibe pago por arreglarlo',
  'Lawn-replacement rebates from your own water utility, calculated for your yard.':
    'Reembolsos por reemplazar césped de tu propia compañía de agua, calculados para tu jardín.',
  'Groundwork gives educational guidance based on published state and local requirements. It is not an official inspection and does not provide evacuation advice.':
    'Groundwork ofrece orientación educativa basada en requisitos estatales y locales publicados. No es una inspección oficial y no da consejos de evacuación.',
  // Home
  'Your properties': 'Tus propiedades',
  'No properties yet': 'Aún no hay propiedades',
  'Add your address and we will look up its fire hazard zone, then walk you through photographing the yard.':
    'Agrega tu dirección y buscaremos su zona de riesgo de incendio; luego te guiaremos para fotografiar el jardín.',
  'Add a property': 'Agregar una propiedad',
  'Loading your properties': 'Cargando tus propiedades',
  Loading: 'Cargando',
  // Quick look card
  'Quick look · ZIP {zip}': 'Vistazo rápido · código {zip}',
  'At this ZIP’s center point · {source}': 'En el punto central de este código · {source}',
  'Fire district': 'Distrito de bomberos',
  'Water utility': 'Compañía de agua',
  'Needs your address': 'Necesita tu dirección',
  Approximate: 'Aproximado',
  'This is a rough snapshot of the area, not your property. {hint} for your exact zone, local rules, and the rebates that apply to you.':
    'Este es un panorama general de la zona, no de tu propiedad. {hint} para conocer tu zona exacta, las reglas locales y los reembolsos que te corresponden.',
  'Enter your full address above': 'Escribe tu dirección completa arriba',
  'Get started below with your full address': 'Comienza abajo con tu dirección completa',
  'Homes here carry the strictest defensible-space obligations in state law, and insurers pay close attention to this zone.':
    'Las casas aquí tienen las obligaciones de espacio defendible más estrictas de la ley estatal, y las aseguradoras vigilan mucho esta zona.',
  'State law requires defensible space around homes here, and new draft rules would tighten the first five feet.':
    'La ley estatal exige espacio defendible alrededor de las casas aquí, y nuevas reglas en borrador endurecerían los primeros cinco pies.',
  'Defensible-space law applies in this zone. Good preparation here is cheaper than in the higher zones.':
    'La ley de espacio defendible aplica en esta zona. Prepararse bien aquí cuesta menos que en las zonas más altas.',
  'No mapped wildfire hazard zone at this point; water-wise landscaping and rebates are likely the bigger win.':
    'No hay zona de riesgo de incendio mapeada en este punto; el paisajismo de bajo consumo de agua y los reembolsos son probablemente la mayor ganancia.',
  'This point is outside the maps we host. A full address may still resolve, or sit outside California.':
    'Este punto está fuera de los mapas que alojamos. Una dirección completa aún puede resolverse, o estar fuera de California.',
  // Zone badge + risk meter
  '{zone} fire hazard zone': 'Zona de riesgo de incendio: {zone}',
  'Very High': 'Muy alta',
  High: 'Alta',
  Moderate: 'Moderada',
  'Non-Wildland': 'No silvestre',
  'Not determined': 'No determinada',
  'Non-wildland': 'No silvestre',
  'Very high': 'Muy alta',
  // Property screen
  'Where to next': 'Qué sigue',
  'Quick check': 'Chequeo rápido',
  'Two minutes, no camera. Same rulebook, same citations.':
    'Dos minutos, sin cámara. Mismo reglamento, mismas citas.',
  'Full scan with photos': 'Escaneo completo con fotos',
  'Seven photographs so the model can flag what you might walk past.':
    'Siete fotografías para que el modelo detecte lo que podrías pasar por alto.',
  'What is your lawn worth?': '¿Cuánto vale tu césped?',
  'Outline it on a satellite view; we measure and price the rebate.':
    'Márcalo en la vista satelital; lo medimos y calculamos el reembolso.',
  'Local programmes': 'Programas locales',
  'Chipping, cost-share, and inspections from agencies near you.':
    'Trituración, costos compartidos e inspecciones de agencias cercanas.',
  'Local responsibility area': 'Área de responsabilidad local',
  'State responsibility area': 'Área de responsabilidad estatal',
  'Properties in a Very High zone carry defensible-space obligations under state law, and would be covered by the proposed Zone 0 rule for the first five feet.':
    'Las propiedades en zona Muy Alta tienen obligaciones de espacio defendible bajo la ley estatal, y estarían cubiertas por la regla propuesta Zona 0 para los primeros cinco pies.',
  Edit: 'Editar',
  Property: 'Propiedad',
  // New property
  'Where is it?': '¿Dónde está?',
  'Address or ZIP code': 'Dirección o código postal',
  'Start typing and pick your address, or enter just a ZIP for a quick look.':
    'Empieza a escribir y elige tu dirección, o pon solo el código postal para un vistazo.',
  'Name it (optional)': 'Ponle nombre (opcional)',
  'Look up my zone': 'Buscar mi zona',
  'Enter coordinates instead': 'Mejor escribir coordenadas',
  'Taking a quick look at {zip}…': 'Echando un vistazo a {zip}…',
  'Place it yourself': 'Ubícala tú mismo',
  'We could not look that address up. Enter the coordinates instead; your phone’s map app can copy them from a dropped pin.':
    'No pudimos encontrar esa dirección. Escribe las coordenadas; la app de mapas de tu teléfono puede copiarlas de un pin.',
  Home: 'Casa',
  'Add a property_title': 'Agregar una propiedad',
  // Quick check
  'Loading the questions': 'Cargando las preguntas',
  Yes: 'Sí',
  No: 'No',
  Skip: 'Omitir',
  Back: 'Atrás',
  "That's Everything!": '¡Eso es todo!',
  'Your plan is built from the same rulebook, with the same citations, as a full scan. The one thing it does not have is our model’s second opinion on your photographs. You can add that any time by running a full scan on the same property.':
    'Tu plan se construye con el mismo reglamento y las mismas citas que un escaneo completo. Lo único que le falta es la segunda opinión de nuestro modelo sobre tus fotografías. Puedes agregarla cuando quieras con un escaneo completo de la misma propiedad.',
  'Show me my plan': 'Muéstrame mi plan',
  'Skipped questions do not count either way. We never assume a hazard you did not confirm.':
    'Las preguntas omitidas no cuentan en ningún sentido. Nunca asumimos un riesgo que no confirmaste.',
  'The first five feet': 'Los primeros cinco pies',
  'Five to thirty feet': 'De cinco a treinta pies',
  'Thirty to a hundred feet': 'De treinta a cien pies',
  'The house itself': 'La casa misma',
  // Result page
  'Your plan': 'Tu plan',
  'Working out your plan': 'Preparando tu plan',
  'Readiness score': 'Puntaje de preparación',
  'Required by law': 'Exigido por ley',
  Recommended: 'Recomendado',
  Done: 'Hecho',
  'What this score means': 'Qué significa este puntaje',
  'You are meeting {met} of {total} points of what applies to your property.':
    'Cumples {met} de {total} puntos de lo que aplica a tu propiedad.',
  'Show the working': 'Ver el cálculo',
  'Hide the working': 'Ocultar el cálculo',
  'New here? Take the 30-second tour': '¿Primera vez? Haz el recorrido de 30 segundos',
  'Nice work. Your score moved from {from} to {to}.':
    'Buen trabajo. Tu puntaje subió de {from} a {to}.',
  Strong: 'Sólido',
  'Getting there': 'En camino',
  'Needs work': 'Necesita trabajo',
  'At risk': 'En riesgo',
  'Your yard broadly meets the rules that apply to it. Keep it maintained, especially through fire season, and re-check after windstorms.':
    'Tu jardín cumple en general las reglas que le aplican. Mantenlo, sobre todo en temporada de incendios, y revísalo después de vientos fuertes.',
  'Most of what applies is met, but real gaps remain. The items below close them, starting with anything the law requires today.':
    'Cumples la mayor parte, pero quedan brechas reales. Los puntos de abajo las cierran, empezando por lo que la ley exige hoy.',
  'Several rules that apply to your property are not met yet. Start with the items required by law; they matter most to inspectors and insurers.':
    'Varias reglas que aplican a tu propiedad aún no se cumplen. Empieza por lo exigido por ley; es lo que más pesa para inspectores y aseguradoras.',
  'Most of what applies to your property is unmet. The plan below is ordered so the highest-stakes work comes first; even one afternoon moves this number.':
    'La mayor parte de lo que aplica a tu propiedad no se cumple. El plan está ordenado para que lo más importante vaya primero; incluso una tarde mueve este número.',
  '{n} of these {isAre} required by law today. Those come first.':
    '{n} de estos puntos {isAre} exigidos por ley hoy. Esos van primero.',
  is: 'está',
  are: 'están',
  'Mark done · score goes to {score}': 'Marcar hecho · el puntaje sube a {score}',
  'Mark done': 'Marcar hecho',
  'About {n}h': 'Aprox. {n} h',
  'No cost': 'Sin costo',
  'Nothing outstanding': 'Nada pendiente',
  'Every rule that applies to your property is met, based on what you photographed and answered.':
    'Todas las reglas que aplican a tu propiedad se cumplen, según lo que fotografiaste y respondiste.',
  'Documentation for your insurer': 'Documentación para tu aseguradora',
  'A PDF of this assessment: your zone, your score, the work you have completed with its photographs, and what is still outstanding. It is your own documentation, not an inspection or a certification.':
    'Un PDF de esta evaluación: tu zona, tu puntaje, el trabajo completado con sus fotografías y lo que sigue pendiente. Es tu propia documentación, no una inspección ni una certificación.',
  'Create the document': 'Crear el documento',
  'Back to my property': 'Volver a mi propiedad',
  'How this is calculated': 'Cómo se calcula',
  'Rulebook {version}': 'Reglamento {version}',
  'Required now': 'Obligatorio ahora',
  'Proposed, not yet law': 'Propuesto, aún no es ley',
  // Tour
  'Tour · {n} of {total}': 'Recorrido · {n} de {total}',
  Next: 'Siguiente',
  'Got it': 'Entendido',
  'Your readiness score': 'Tu puntaje de preparación',
  'From 0 to 100, computed from the state and local rules that actually apply to your property. The color and the word tell you the band at a glance.':
    'De 0 a 100, calculado con las reglas estatales y locales que realmente aplican a tu propiedad. El color y la palabra te dicen el nivel de un vistazo.',
  'The three counts': 'Los tres conteos',
  'What the law requires today, what is recommended on top of that, and what you have already finished.':
    'Lo que la ley exige hoy, lo que se recomienda además, y lo que ya terminaste.',
  'What it means': 'Qué significa',
  'The score in plain words. "Show the working" opens every rule behind the number, each with its citation, so nothing here is a black box.':
    'El puntaje en palabras simples. "Ver el cálculo" muestra cada regla detrás del número, con su cita, para que nada sea una caja negra.',
  'Each card is one task, with its legal status, rough time and cost, and the exact score you will have once it is done. Mark it done and the number at the top updates immediately.':
    'Cada tarjeta es una tarea, con su estado legal, tiempo y costo aproximados, y el puntaje exacto que tendrás al terminarla. Márcala como hecha y el número de arriba se actualiza al instante.',
  'Take it with you': 'Llévalo contigo',
  'Create a PDF of the whole assessment for your records or your insurer. It is your documentation, not an official inspection.':
    'Crea un PDF de toda la evaluación para tus archivos o tu aseguradora. Es tu documentación, no una inspección oficial.',
  // Settings / account
  Settings: 'Configuración',
  Account: 'Cuenta',
  'Signed in.': 'Sesión iniciada.',
  'A private account on this device. No email, nothing shared.':
    'Una cuenta privada en este dispositivo. Sin correo, nada compartido.',
  Language: 'Idioma',
  'Sign out': 'Cerrar sesión',
  'Your properties and scans stay saved for next time.':
    'Tus propiedades y escaneos quedan guardados para la próxima.',
  'Delete everything': 'Borrar todo',
  'Removes your account, properties, scans, and every photo file. This cannot be undone. Type DELETE to confirm.':
    'Elimina tu cuenta, propiedades, escaneos y cada archivo de foto. No se puede deshacer. Escribe DELETE para confirmar.',
  'Permanently delete my account': 'Eliminar mi cuenta permanentemente',
  // Sign in
  'Your account': 'Tu cuenta',
  'Welcome back': 'Bienvenido de nuevo',
  'Create your account': 'Crea tu cuenta',
  'Your properties, scans, and plan are where you left them.':
    'Tus propiedades, escaneos y plan están donde los dejaste.',
  'Eight characters or more for the password. Your data stays yours.':
    'Ocho caracteres o más para la contraseña. Tus datos siguen siendo tuyos.',
  Email: 'Correo electrónico',
  Password: 'Contraseña',
  'Sign in': 'Iniciar sesión',
  'Create account': 'Crear cuenta',
  'New here? Create an account': '¿Primera vez? Crea una cuenta',
  'Have an account? Sign in': '¿Ya tienes cuenta? Inicia sesión',
  // Impact band
  'So far, with our testers': 'Hasta ahora, con quienes lo prueban',
  '{n} yards assessed': '{n} jardines evaluados',
  '{n} tasks completed': '{n} tareas completadas',
  '${n} in rebates identified': '${n} en reembolsos identificados',
  '{n} gallons/yr in savings mapped': '{n} galones/año de ahorro mapeados',
  // Navigation titles
  'Edit property': 'Editar propiedad',
  'Measure a lawn': 'Medir un césped',
  'Yard scan': 'Escaneo del jardín',
  Photograph: 'Fotografiar',
  'A few questions': 'Unas preguntas',
  'What we spotted': 'Lo que detectamos',
  // Unresolved caveat
  'We could not determine your {things}. Rather than guess, we have left it blank. The wrong agency would send you to the wrong place.':
    'No pudimos determinar tu {things}. En vez de adivinar, lo dejamos en blanco. La agencia equivocada te mandaría al lugar equivocado.',
  ' or ': ' ni ',
  'fire hazard zone': 'zona de riesgo de incendio',
  'fire district': 'distrito de bomberos',
  'water utility': 'compañía de agua',
  // Privacy note
  'Your data stays yours': 'Tus datos siguen siendo tuyos',
  'Photos are visible only to you, location data is stripped from them before upload, and deleting a property or your account erases the actual files, not just the records.':
    'Solo tú ves tus fotos, se les quita la ubicación antes de subirlas, y borrar una propiedad o tu cuenta elimina los archivos reales, no solo los registros.',
};
