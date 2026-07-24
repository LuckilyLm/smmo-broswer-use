import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import { enUS } from "./locales/en-US";
import { zhCN } from "./locales/zh-CN";

export const LOCALE_STORAGE_KEY = "leadflow_locale";
export type AppLocale = "en-US" | "zh-CN";

function initialLocale(): AppLocale {
  const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY);
  if (stored === "en-US" || stored === "zh-CN") return stored;
  return window.navigator.language.toLowerCase().startsWith("zh") ? "zh-CN" : "en-US";
}

void i18n.use(initReactI18next).init({
  resources: {
    "en-US": { translation: enUS },
    "zh-CN": { translation: zhCN }
  },
  lng: initialLocale(),
  fallbackLng: "en-US",
  supportedLngs: ["en-US", "zh-CN"],
  interpolation: { escapeValue: false },
  returnNull: false
});

export async function setAppLocale(locale: AppLocale) {
  window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  await i18n.changeLanguage(locale);
}

export default i18n;
