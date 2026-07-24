import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiError, apiGet } from "../api";

export function useResource<T>(path: string, fallback: T) {
  const { t } = useTranslation();
  const [data, setData] = useState<T>(fallback);
  const [loading, setLoading] = useState(Boolean(path));
  const [error, setError] = useState<string | null>(null);
  const refresh = async () => {
    if (!path) return;
    setLoading(true);
    setError(null);
    try {
      setData(await apiGet<T>(path));
    } catch (err) {
      setError(err instanceof ApiError && err.status === 403 ? t("common.permissionDenied") : t("common.requestFailed"));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    let cancelled = false;
    if (!path) return () => { cancelled = true; };
    setLoading(true);
    setError(null);
    apiGet<T>(path)
      .then((value) => { if (!cancelled) setData(value); })
      .catch((err) => { if (!cancelled) setError(err instanceof ApiError && err.status === 403 ? t("common.permissionDenied") : t("common.requestFailed")); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [path, t]);
  return { data, loading, error, refresh };
}
