import net from "node:net";

const METADATA_IPS = new Set(["169.254.169.254", "100.100.100.200"]);

function parseAllowlist(raw: string | undefined) {
  return (raw ?? "")
    .split(",")
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean);
}

function isPrivateIpAddress(hostname: string) {
  const ipVersion = net.isIP(hostname);
  if (!ipVersion) return false;
  if (METADATA_IPS.has(hostname)) return true;
  if (hostname === "127.0.0.1" || hostname === "0.0.0.0") return true;
  if (hostname.startsWith("10.") || hostname.startsWith("192.168.")) return true;
  if (/^172\.(1[6-9]|2\d|3[0-1])\./.test(hostname)) return true;
  if (hostname.startsWith("169.254.")) return true;
  if (hostname === "::1" || hostname.startsWith("fc") || hostname.startsWith("fd") || hostname.startsWith("fe80:")) return true;
  return false;
}

function isPrivateHostname(hostname: string) {
  const normalized = hostname.trim().toLowerCase();
  if (!normalized) return true;
  if (["localhost", "host.docker.internal"].includes(normalized)) return true;
  if (normalized.endsWith(".local") || normalized.endsWith(".internal") || normalized.endsWith(".localhost")) return true;
  return isPrivateIpAddress(normalized);
}

function isHostAllowlisted(hostname: string, allowlist: string[]) {
  if (allowlist.length === 0) return true;
  const normalized = hostname.toLowerCase();
  return allowlist.some((allowed) => normalized === allowed || normalized.endsWith(`.${allowed}`));
}

function validateExternalUrl(
  rawUrl: string | null | undefined,
  options: {
    allowInsecure: boolean;
    allowPrivateNetwork: boolean;
    allowlistEnv?: string;
    kind: "callback" | "manifest";
  }
) {
  if (!rawUrl) return null;
  let parsed: URL;
  try {
    parsed = new URL(rawUrl);
  } catch {
    throw new Error(`Invalid ${options.kind} URL.`);
  }

  const allowlist = parseAllowlist(options.allowlistEnv);
  if (!isHostAllowlisted(parsed.hostname, allowlist)) {
    throw new Error(`The ${options.kind} host is not allowlisted.`);
  }

  if (parsed.protocol !== "https:" && !(options.allowInsecure && parsed.protocol === "http:")) {
    throw new Error(`The ${options.kind} URL must use HTTPS.`);
  }

  if (!options.allowPrivateNetwork && isPrivateHostname(parsed.hostname)) {
    throw new Error(`Private-network ${options.kind} URLs are blocked by policy.`);
  }

  return parsed.toString();
}

export function normalizeCallbackUrl(url: string | null | undefined) {
  return validateExternalUrl(url, {
    allowInsecure: process.env.OCR_PUBLIC_ALLOW_INSECURE_CALLBACKS === "true",
    allowPrivateNetwork: process.env.OCR_PUBLIC_ALLOW_PRIVATE_NETWORK_URLS === "true",
    allowlistEnv: process.env.OCR_PUBLIC_CALLBACK_HOST_ALLOWLIST,
    kind: "callback",
  });
}

export function normalizeManifestFileUrl(url: string) {
  const normalized = validateExternalUrl(url, {
    allowInsecure: process.env.OCR_PUBLIC_ALLOW_INSECURE_MANIFEST_FETCH === "true",
    allowPrivateNetwork: process.env.OCR_PUBLIC_ALLOW_PRIVATE_NETWORK_URLS === "true",
    allowlistEnv: process.env.OCR_PUBLIC_MANIFEST_HOST_ALLOWLIST,
    kind: "manifest",
  });
  if (!normalized) {
    throw new Error("Manifest URL is required.");
  }
  return normalized;
}
