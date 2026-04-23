const MAX_DIM = 2048;

export async function resizeImageToFile(
  file: File,
  maxBytes: number,
  maxDim = MAX_DIM,
): Promise<File> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);

    img.onload = () => {
      URL.revokeObjectURL(url);

      let { width, height } = img;
      if (width > maxDim || height > maxDim) {
        if (width >= height) {
          height = Math.round((height / width) * maxDim);
          width = maxDim;
        } else {
          width = Math.round((width / height) * maxDim);
          height = maxDim;
        }
      }

      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      canvas.getContext("2d")!.drawImage(img, 0, 0, width, height);

      const baseName = file.name.replace(/\.[^.]+$/, "");

      const tryQuality = (quality: number) => {
        canvas.toBlob(
          (blob) => {
            if (!blob) { reject(new Error("Resize failed")); return; }
            if (blob.size <= maxBytes || quality <= 0.3) {
              resolve(new File([blob], `${baseName}.jpg`, { type: "image/jpeg" }));
            } else {
              tryQuality(Math.round((quality - 0.1) * 10) / 10);
            }
          },
          "image/jpeg",
          quality,
        );
      };

      tryQuality(0.85);
    };

    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Could not load image")); };
    img.src = url;
  });
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
