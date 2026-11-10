const MAX_DIM = 2048;

function canvasToJpegBlob(canvas: HTMLCanvasElement, quality: number): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
}

// Recompresses at progressively lower quality until under maxBytes, or quality bottoms out.
async function shrinkToJpeg(canvas: HTMLCanvasElement, maxBytes: number): Promise<Blob> {
  let quality = 0.85;
  for (;;) {
    const blob = await canvasToJpegBlob(canvas, quality);
    if (!blob) throw new Error("Resize failed");
    if (blob.size <= maxBytes || quality <= 0.3) return blob;
    quality = Math.round((quality - 0.1) * 10) / 10;
  }
}

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

      shrinkToJpeg(canvas, maxBytes)
        .then((blob) => resolve(new File([blob], `${baseName}.jpg`, { type: "image/jpeg" })))
        .catch(reject);
    };

    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Could not load image")); };
    img.src = url;
  });
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
