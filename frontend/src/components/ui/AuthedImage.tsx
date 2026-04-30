import { useEffect, useState } from "react";
import { getAuthToken } from "@/api/client";

interface Props extends React.ImgHTMLAttributes<HTMLImageElement> {
  src: string;
}

export function AuthedImage({ src, ...props }: Props) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;

    async function load() {
      const token = await getAuthToken();
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch(src, { headers, credentials: "include" });
      if (!res.ok || cancelled) return;

      const blob = await res.blob();
      if (cancelled) return;

      objectUrl = URL.createObjectURL(blob);
      setBlobUrl(objectUrl);
    }

    load().catch(() => {});

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [src]);

  if (!blobUrl) return null;
  return <img src={blobUrl} {...props} />;
}
