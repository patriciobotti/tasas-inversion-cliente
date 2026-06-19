# Bot de tasas de inversion - Estudio Botti

Este repositorio busca automaticamente, una vez por dia, la TNA vigente de
los 5 instrumentos de inversion habilitados para el cliente, y publica un
archivo `tasas.json` que el artifact del cliente consulta para recomendar
donde invertir.

## Que hace

1. Una vez por dia (8:00 hora Argentina), GitHub Actions ejecuta `buscar_tasas.py`
2. El script le pide a Claude que busque en la web la TNA actual de:
   - Banco Galicia (FIMA Premium)
   - Banco Macro (Pionero Pesos Plus)
   - Banco Santander (Super Ahorro)
   - Mercado Pago (Mercado Fondo)
   - Cocos Capital (Cocos Ahorro FCI)
3. Guarda el resultado en `public/tasas.json`
4. Publica ese archivo en GitHub Pages (queda accesible en una URL publica)
5. Tambien agrega una fila por instrumento en una Google Sheet, para que
   Pato pueda revisar el historico manualmente

## Configuracion inicial (una sola vez)

### 1. Crear el repositorio en GitHub

Subi esta carpeta completa a un repositorio nuevo, por ejemplo
`estudio-botti/tasas-inversion-cliente`. Puede ser privado.

### 2. Habilitar GitHub Pages

En el repositorio: Settings -> Pages -> Source: "Deploy from a branch" ->
Branch: `gh-pages` (esa rama la crea sola la primera vez que corre el workflow).

Despues de la primera ejecucion exitosa, el archivo va a quedar accesible en:

```
https://estudio-botti.github.io/tasas-inversion-cliente/tasas.json
```

(ajustar usuario/nombre de repo segun corresponda)

### 3. Cargar los Secrets

En el repositorio: Settings -> Secrets and variables -> Actions -> New repository secret.
Cargar estos tres:

| Nombre del secret | Valor |
|---|---|
| `ANTHROPIC_API_KEY` | La API key generada en console.anthropic.com |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | El contenido completo del archivo .json de la cuenta de servicio (pegar todo el JSON como texto) |
| `GOOGLE_SHEET_ID` | El ID de la Google Sheet (es la parte de la URL entre `/d/` y `/edit`) |

### 4. Probarlo manualmente antes de esperar al cron

En el repositorio: pestaña "Actions" -> "Actualizar tasas de inversion" ->
"Run workflow". Esto lo ejecuta ya mismo sin esperar al horario programado,
util para validar que todo esta bien configurado.

### 5. Verificar el resultado

- Revisar que el JSON se publico bien abriendo la URL de GitHub Pages
- Revisar que la Google Sheet recibio las 5 filas nuevas
- Si algo falla, el log del error queda visible en la pestaña "Actions",
  dentro de la ejecucion que fallo

## Archivos

- `buscar_tasas.py` - script principal
- `requirements.txt` - dependencias de Python
- `.github/workflows/actualizar_tasas.yml` - configuracion de la ejecucion automatica diaria

## Proximo paso

Una vez que este archivo `tasas.json` se este actualizando solo todos los
dias, el siguiente paso es armar el artifact que el cliente va a usar para
consultar. Ese artifact va a hacer un `fetch()` a la URL de GitHub Pages
para traer las tasas del dia, y despues llamar a la API de Claude con esas
tasas + las reglas de decision para generar la recomendacion.
