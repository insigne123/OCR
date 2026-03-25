const DEFAULT_OCR_API_URL = "http://127.0.0.1:8000";

export function getOcrApiUrl() {
  return (process.env.OCR_API_URL || DEFAULT_OCR_API_URL).replace(/\/$/, "");
}

export function getOptionalOcrApiKey() {
  return process.env.OCR_API_KEY || null;
}
