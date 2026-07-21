# Guía de configuración — Dashboard HTML automático (Python + GitHub)

Con esto vas a tener un reporte en HTML, con tarjetas de KPIs y gráficas
interactivas, que se actualiza **solo, todos los días**, sin que tu PC
esté prendido — corre en los servidores de GitHub (gratis).

Al final vas a tener un link fijo tipo:
`https://TU-USUARIO.github.io/reporte-mesa-ayuda/`

Tiempo estimado: 15 minutos, una sola vez.

---

## Paso 1 — Crear cuenta y repositorio en GitHub
1. Si no tienes cuenta, créala gratis en [github.com](https://github.com).
2. Haz clic en **"New repository"** (botón verde).
3. Nombre sugerido: `reporte-mesa-ayuda`.
4. Márcalo como **Público** (necesario para usar GitHub Pages gratis) o
   privado si tienes plan que lo permita.
5. Dale a **Create repository**.

## Paso 2 — Subir los archivos
Sube estos 3 archivos/carpetas que te generé, manteniendo la misma
estructura de carpetas:

```
reporte-mesa-ayuda/
├── generar_reporte.py
├── requirements.txt
└── .github/
    └── workflows/
        └── actualizar_reporte.yml
```

La forma más fácil: en la página del repo, dale a **"Add file" → "Upload files"**
y arrastra los archivos (asegúrate de que la carpeta `.github/workflows/`
quede exactamente con ese nombre y esa ruta).

## Paso 3 — Guardar tus credenciales de Freshservice como "Secrets"
Esto es importante: así tu API Key **nunca queda visible** en el código.

1. En tu repositorio, ve a **Settings → Secrets and variables → Actions**.
2. Haz clic en **"New repository secret"**.
3. Crea estos dos secrets:
   - Nombre: `FRESHSERVICE_DOMAIN` → Valor: tu dominio
     (ej. si entras a `capitalmedellin.freshservice.com`, el valor es `capitalmedellin`)
   - Nombre: `FRESHSERVICE_API_KEY` → Valor: tu API Key
     (la sacas en Freshservice → tu perfil → "Profile Settings" → API Key)

## Paso 4 — Activar GitHub Pages
1. Ve a **Settings → Pages**.
2. En "Source", selecciona la rama `main` y la carpeta `/ (root)`.
3. Dale a **Save**.
4. GitHub te va a dar un link (tarda 1-2 minutos en activarse), algo así:
   `https://TU-USUARIO.github.io/reporte-mesa-ayuda/`

## Paso 5 — Correrlo por primera vez manualmente
1. Ve a la pestaña **Actions** de tu repositorio.
2. Vas a ver el workflow **"Actualizar Reporte Freshservice"**.
3. Haz clic en él, luego en **"Run workflow"** (botón a la derecha) → **Run workflow**.
4. Espera 1-2 minutos y actualiza la página. Debe verse en verde (✓) si todo salió bien.
5. Entra a tu link de GitHub Pages — ya debe mostrar el dashboard con tus tickets reales.

## ¿Qué pasa después de esto?
Nada más que hacer. Todos los días a las **7:00 a.m. hora Colombia**, GitHub
va a:
1. Conectarse a Freshservice
2. Traer los tickets actualizados
3. Recalcular las métricas
4. Publicar el HTML actualizado en tu link

Puedes compartir ese link con tu jefe o tu equipo — siempre va a mostrar
los datos del día.

## Si algo falla
- Ve a la pestaña **Actions** → haz clic en la ejecución que falló (ícono ❌)
  → ahí puedes ver el error exacto (casi siempre es un typo en el dominio
  o la API Key).
- Si tu categoría (CCTV, accesorios, impresión, radios, etc.) no coincide
  con los "grupos" de Freshservice, dime el nombre exacto del campo
  personalizado que usas y ajusto el script para clasificar por ahí.

## Cambiar la hora de actualización
La línea `cron: '0 12 * * *'` en el archivo `actualizar_reporte.yml`
controla la hora (está en UTC). Si quieres otra hora o que corra varias
veces al día, dime y te la ajusto.
