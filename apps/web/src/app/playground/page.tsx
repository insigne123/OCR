import { AppShell } from "@/components/app-shell";
import { PlaygroundClient } from "@/components/playground-client";
import { requireAuthenticatedAppUser } from "@/lib/auth";

export default async function PlaygroundPage() {
  await requireAuthenticatedAppUser();
  return (
    <AppShell
      activeSection="playground"
      eyebrow="API playground"
      title="OCR JSON Playground"
      subtitle="Sube un documento o imagen y prueba el endpoint principal del producto. La salida principal es JSON canónico listo para integración."
    >
      <PlaygroundClient />
    </AppShell>
  );
}
