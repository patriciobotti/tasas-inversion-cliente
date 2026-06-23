# Despliegue en Vercel

Esta carpeta agrega una pagina web propia (`public_app/index.html`) y una
funcion backend (`api/recomendar.js`) que juntas reemplazan al artifact que
no podia llamar directo a la API por la restriccion de CSP del navegador.

## Como funciona

1. El cliente abre la pagina (sin necesidad de cuenta de ningun tipo)
2. Escribe el monto y elige el plazo, click en "Consultar recomendacion"
3. La pagina llama a `/api/recomendar` (la funcion backend, NO a la API de
   Claude directamente)
4. Esa funcion, que corre en el servidor de Vercel (no en el navegador del
   cliente), busca las tasas del dia en GitHub Pages y llama a la API de
   Claude usando tu API key, guardada de forma segura
5. La funcion le devuelve la recomendacion a la pagina, que la muestra

La API key NUNCA viaja al navegador del cliente, vive solo en el servidor.

## Pasos para desplegar

### 1. Subir estos archivos nuevos al repositorio de GitHub

Subi estos 4 elementos nuevos a tu repositorio `tasas-inversion-cliente`
(el mismo de siempre, junto al `buscar_tasas.py` y el resto):

- `api/recomendar.js`
- `public_app/index.html`
- `vercel.json`
- `package.json`

### 2. Conectar el repositorio en Vercel

1. Entra a vercel.com, ya logueado con tu cuenta de GitHub
2. Click en "Add New..." -> "Project"
3. Busca y selecciona el repositorio `tasas-inversion-cliente`
4. Click en "Import"
5. NO hace falta tocar la configuracion de build (el archivo `vercel.json`
   ya le dice a Vercel como armar todo)

### 3. Configurar la variable de entorno (la API key)

Antes de hacer "Deploy", o despues entrando a la configuracion del
proyecto:

1. En la pantalla de configuracion del proyecto, busca la seccion
   "Environment Variables"
2. Agrega una nueva:
   - Name: `ANTHROPIC_API_KEY`
   - Value: tu API key de Anthropic (la misma que usas en el script de
     GitHub Actions)
3. Guarda

### 4. Desplegar

Click en "Deploy". Vercel va a tardar uno o dos minutos en armar todo.
Cuando termine, te va a dar una URL del tipo:

```
https://tasas-inversion-cliente.vercel.app
```

Esa es la URL que le compartis a tu cliente. Funciona sin cuenta, sin
login, para cualquiera que abra el link.

## Actualizaciones futuras

Cada vez que hagas un cambio y subas un commit nuevo al repositorio de
GitHub (a la rama `main`), Vercel va a re-desplegar automaticamente la
version actualizada, sin que tengas que hacer nada manual en Vercel.
