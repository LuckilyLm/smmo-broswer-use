import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";

interface RunOptions {
  successMessage?: string;
  errorMessage?: string;
  onSuccess?: () => void;
  onError?: () => void;
}

export function useAsyncAction() {
  const { t } = useTranslation();
  const [runningKeys, setRunningKeys] = useState<Set<string>>(new Set());

  const isRunning = useCallback((key: string) => runningKeys.has(key), [runningKeys]);

  const run = useCallback(
    async <T>(key: string, action: () => Promise<T>, options: RunOptions = {}) => {
      if (runningKeys.has(key)) return;
      setRunningKeys((prev) => new Set(prev).add(key));
      try {
        const result = await action();
        if (options.successMessage) {
          console.log(options.successMessage);
        }
        options.onSuccess?.();
        return result;
      } catch (err) {
        if (options.errorMessage) {
          console.error(options.errorMessage);
        } else {
          console.error(t("common.requestFailed"));
        }
        options.onError?.();
        throw err;
      } finally {
        setRunningKeys((prev) => {
          const next = new Set(prev);
          next.delete(key);
          return next;
        });
      }
    },
    [runningKeys, t]
  );

  return { isRunning, run, runningKeys };
}
