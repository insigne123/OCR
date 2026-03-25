# GrupoExpro Trial on VM

Esta es la ruta mas simple: correr `apps/web` y `services/ocr-api` en la VM `ocr-lowcost-vm` y exponer todo con Nginx.

Proyecto:

- GCP project id: `leadflowai-3yjcy`
- VM: `ocr-lowcost-vm`

## Arquitectura recomendada

- `apps/web` en `127.0.0.1:3000`
- `services/ocr-api` en `127.0.0.1:8000`
- `nginx` publica:
  - `https://TU_IP_O_DOMINIO/` -> web
  - `https://TU_IP_O_DOMINIO/v1/*` -> OCR API

Con esto el trial de GrupoExpro usa la web y la web internamente llama al OCR API local.

## 1. Entrar a la VM

Desde Cloud Shell o tu terminal:

```bash
gcloud compute ssh ocr-lowcost-vm --zone us-central1-a --project leadflowai-3yjcy
```

## 2. Instalar runtime base

En la VM:

```bash
sudo apt update
sudo apt install -y git curl nginx python3.12 python3.12-venv python3-pip build-essential
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
```

Verifica:

```bash
node -v
npm -v
python3.12 --version
```

## 3. Clonar el repo

```bash
sudo mkdir -p /opt/ocr-platform
sudo chown $USER:$USER /opt/ocr-platform
git clone https://github.com/insigne123/OCR.git /opt/ocr-platform
cd /opt/ocr-platform
```

## 4. Instalar dependencias

### Python

```bash
python3.12 -m venv /opt/ocr-platform/.venv
source /opt/ocr-platform/.venv/bin/activate
pip install --upgrade pip
pip install -e /opt/ocr-platform/services/ocr-api
```

### Node

```bash
cd /opt/ocr-platform
npm install
npm run build:web
```

## 5. Crear usuario de servicio

```bash
sudo useradd -r -s /bin/bash -d /opt/ocr-platform ocr || true
sudo chown -R ocr:ocr /opt/ocr-platform
sudo mkdir -p /etc/ocr-platform
sudo chown root:ocr /etc/ocr-platform
sudo chmod 750 /etc/ocr-platform
```

## 6. Configurar variables de entorno

### `/etc/ocr-platform/ocr-api.env`

```bash
OCR_API_KEY=internal-ocr-token
OCR_VISUAL_ENGINE=rapidocr
OCR_STRUCTURED_NORMALIZER_MODE=auto
```

### `/etc/ocr-platform/web.env`

```bash
NODE_ENV=production
PORT=3000
HOSTNAME=127.0.0.1
OCR_API_URL=http://127.0.0.1:8000
OCR_API_KEY=internal-ocr-token
NEXT_PUBLIC_SUPABASE_URL=TU_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY=TU_SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY=TU_SUPABASE_SERVICE_ROLE_KEY
SUPABASE_STORAGE_BUCKET=documents
NEXT_PUBLIC_SITE_URL=http://34.45.246.139
OCR_PUBLIC_ALLOW_DEV_AUTH=false
OCR_TRIAL_API_KEYS=[{"id":"trial-grupoexpro","name":"GrupoExpro Trial","tenantId":"trial-grupoexpro","apiKey":"QpQSZxS2s8oPQOsR5CmTNA2rsBRouVs4DWYKlkflPso","documentLimit":50,"expiresAt":"2026-05-31T23:59:59Z","allowCallbacks":false,"forceProcessingMode":"sync","accessMode":"trial"}]
```

## 7. Instalar systemd services

Desde tu repo local ya quedaron los templates en `deploy/vm/`.

En la VM:

```bash
sudo cp /opt/ocr-platform/deploy/vm/ocr-api.service /etc/systemd/system/ocr-api.service
sudo cp /opt/ocr-platform/deploy/vm/ocr-web.service /etc/systemd/system/ocr-web.service
sudo systemctl daemon-reload
sudo systemctl enable ocr-api ocr-web
sudo systemctl restart ocr-api ocr-web
```

Verifica:

```bash
sudo systemctl status ocr-api --no-pager
sudo systemctl status ocr-web --no-pager
```

## 8. Configurar Nginx

```bash
sudo cp /opt/ocr-platform/deploy/vm/nginx-ocr.conf /etc/nginx/sites-available/ocr-platform
sudo ln -sf /etc/nginx/sites-available/ocr-platform /etc/nginx/sites-enabled/ocr-platform
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

## 9. Abrir firewall

Si usas firewall del SO:

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

En GCP asegúrate de permitir al menos `tcp:80` a la IP externa de la VM.

## 10. Validar

Desde tu computador:

```powershell
Invoke-RestMethod http://34.45.246.139/api/public/trial/v1/health
Invoke-RestMethod http://34.45.246.139/v1/health
```

Probar quota:

```powershell
Invoke-RestMethod http://34.45.246.139/api/public/trial/v1/usage -Headers @{"x-api-key"="QpQSZxS2s8oPQOsR5CmTNA2rsBRouVs4DWYKlkflPso"}
```

## 11. Compartir a GrupoExpro

- Base URL: `http://34.45.246.139/api/public/trial/v1`
- Token: `QpQSZxS2s8oPQOsR5CmTNA2rsBRouVs4DWYKlkflPso`
- Limite: `50 documentos`

## 12. Recomendaciones

- Si usaras esto mas de unos pocos dias, agrega dominio y HTTPS con Certbot.
- Para trial corto, esta VM es suficiente y mucho mas simple que Cloud Run + App Hosting.
