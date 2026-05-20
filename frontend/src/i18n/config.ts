import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "@/locales/en/translation.json";
import de from "@/locales/de/translation.json";
import fr from "@/locales/fr/translation.json";
import es from "@/locales/es/translation.json";
import nl from "@/locales/nl/translation.json";

export const SUPPORTED_LANGUAGES = [
  { code: "en", label: "English" },
  { code: "de", label: "Deutsch" },
  { code: "fr", label: "Français" },
  { code: "es", label: "Español" },
  { code: "nl", label: "Nederlands" },
] as const;

export type LanguageCode = (typeof SUPPORTED_LANGUAGES)[number]["code"];

i18n.use(initReactI18next).init({
  lng: localStorage.getItem("wm_lang") ?? "en",
  fallbackLng: "en",
  resources: {
    en: { translation: en },
    de: { translation: de },
    fr: { translation: fr },
    es: { translation: es },
    nl: { translation: nl },
  },
  interpolation: {
    escapeValue: false,
  },
});

export default i18n;
