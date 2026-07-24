import { afterEach, describe, expect, it } from "vitest";
import i18n, { LOCALE_STORAGE_KEY, setAppLocale } from ".";
import { enUS } from "./locales/en-US";
import { zhCN } from "./locales/zh-CN";

function flattenStrings(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (!value || typeof value !== "object") return [];
  return Object.values(value).flatMap(flattenStrings);
}

function flattenKeys(value: unknown, prefix = ""): string[] {
  if (!value || typeof value !== "object") return [prefix];
  return Object.entries(value).flatMap(([key, child]) => flattenKeys(child, prefix ? `${prefix}.${key}` : key));
}

describe("localization", () => {
  afterEach(async () => {
    window.localStorage.clear();
    await i18n.changeLanguage("en-US");
  });

  it("contains complete menu labels in both locales", async () => {
    await i18n.changeLanguage("en-US");
    expect(i18n.t("nav.executions")).toBe("Executions");
    await i18n.changeLanguage("zh-CN");
    expect(i18n.t("nav.executions")).toBe("执行记录");
    expect(i18n.t("settings.safetyMessage")).toBe("所有回复操作均需要人工确认，系统不会自动发送回复。");
    expect(i18n.t("settings.safetyMessage")).not.toContain("send_disabled");
  });

  it("persists the selected language", async () => {
    await setAppLocale("zh-CN");
    expect(i18n.resolvedLanguage).toBe("zh-CN");
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("zh-CN");
  });

  it("keeps locale keys in parity and blocks known cross-language copy leaks", () => {
    expect(flattenKeys(zhCN).sort()).toEqual(flattenKeys(enUS).sort());
    expect(flattenStrings(enUS).join("\n")).not.toMatch(/[\u3400-\u9fff]/);

    const zhCopy = flattenStrings(zhCN).join("\n").toLowerCase();
    for (const leak of [
      "run id",
      "selected count",
      "author name",
      "final intent level",
      "campaign id",
      "total tokens",
      "discovery_only",
      "send_disabled=true",
      "multi keyword",
      "advanced reports"
    ]) {
      expect(zhCopy).not.toContain(leak);
    }
  });
});
