# Asistente de Reuniones

App de escritorio (Windows, Mac y Linux) que va a las reuniones por ti y te manda el resumen.

```
Google Calendar ──► ¿es inútil? ──► bot de Recall.ai entra a Zoom / Meet / Teams / Webex
                                              │
      Correo + app ◄── resumen de Claude ◄── transcripción (al terminar la reunión)
```

Cada resumen trae: lo esencial en 30 segundos, decisiones, tareas (las tuyas en negrita),
las veces que te mencionaron, si tienes que hacer algo y un veredicto de si la reunión
pudo ser un correo. Te llega por Gmail con la transcripción adjunta y queda en la pestaña
**Resúmenes** de la app.

## La app

- **Próximas reuniones:** tus reuniones de las próximas 24 h y quién va a cada una (🤖 bot o 🙋 tú)
  con el motivo. Elige una y pulsa *Mandar el bot*, *Voy yo* o *Usar mis reglas*
  (doble clic también alterna). Si ya había un bot agendado y cambias a *Voy yo*, se cancela.
- **Resúmenes:** todos los resúmenes, para leerlos sin abrir el correo.
- **Ajustes:** tu nombre, correo, claves y las reglas de qué reuniones son "inútiles".
- **Registro:** lo que ha hecho la app.
- **Modo automático:** revisa cada 5 minutos mientras la app esté abierta (o minimizada).

Reglas por defecto: va el bot si el título tiene `[bot]`, si el evento está pintado de gris
(Grafito) o si el título dice "weekly", "sync", "status", "seguimiento"… Vas tú si la organizas,
son menos de 3 personas, la rechazaste o el título dice "1:1", "entrevista", "cliente", etc.

Tus datos (ajustes, claves, resúmenes) se guardan en la carpeta `AsistenteReuniones` de tu
usuario. El botón *Abrir carpeta de datos* te lleva ahí.

## 1. Consigue la app

Necesitas Python una sola vez: descárgalo de python.org/downloads y, en la primera pantalla
del instalador de Windows, marca **"Add python.exe to PATH"**.

**Lo más simple: doble clic en `Iniciar (Windows).bat`** (en Mac: `Iniciar (Mac).command`).
La primera vez tarda 1–2 minutos preparando todo; después abre la app al instante.
Si Windows avisa, pulsa *Más información* → *Ejecutar de todas formas*.

**Si prefieres un .exe:** doble clic en `Crear ejecutable (Windows).bat`. En 3–5 minutos te abre
la carpeta con `Asistente de Reuniones.exe`; crea un acceso directo en el escritorio y listo
(ya no necesitarás los .bat). En Mac/Linux: `python3 construir.py`.

**Sin instalar Python:** sube esta carpeta a un repositorio de GitHub, ve a
*Actions → Construir app → Run workflow* y descarga el .zip para Windows o Mac.

> En Mac, la primera vez macOS dirá que la app es de un desarrollador no identificado:
> clic derecho sobre ella → *Abrir* → *Abrir*. En Windows, si SmartScreen avisa:
> *Más información* → *Ejecutar de todas formas*. Pasa porque la app no está firmada.

### Si no se instala en algún computador

- **Primero descomprime.** Si abres `Iniciar` desde dentro del .zip no funciona: clic derecho
  sobre el .zip → *Extraer todo…* y abre la carpeta extraída.
- **No copies la carpeta `.venv` de otro computador.** Ahora el iniciador lo detecta y la rehace
  solo, pero lo más limpio es copiar la carpeta sin `.venv`.
- **Python de Microsoft Store o sin "tcl/tk":** instala el de python.org; si ya lo tienes,
  abre su instalador → *Modify* → marca *tcl/tk and IDLE*.
- **Red de empresa:** muchas bloquean las descargas de Python (pip). Prueba con otra red o
  usa el .exe ya construido (GitHub Actions, abajo).
- **Mac con Intel vs. chip Apple:** GitHub Actions ahora construye ambas versiones
  (`Mac-Intel` y `Mac-AppleSilicon`); descarga la que corresponde.
- Si algo falla, el iniciador muestra las últimas líneas de `instalacion.log`, y si la app no
  arranca aparece una ventana con el error (también queda en `error_arranque.txt`).

## 2. Configúrala (una sola vez, ~20 min)

Abre la app y ve a **Ajustes**:

1. **Tu nombre, correo y nombre del bot.**
2. **Clave de Recall.ai** — crea una cuenta en recall.ai, copia la API key y elige la región
   en que quedó tu cuenta. Recall cobra por hora de bot grabando; revisa su página de precios.
3. **Clave de Anthropic** — créala en console.anthropic.com.
4. **Google:**
   1. En console.cloud.google.com crea un proyecto.
   2. Activa **Google Calendar API** y **Gmail API**.
   3. En *Google Auth Platform* configura la pantalla de consentimiento (tipo *External*) y
      agrégate como *usuario de prueba*.
   4. Crea un cliente OAuth tipo **App de escritorio** y descarga el JSON.
   5. En la app: *Elegir credentials.json…* → elige ese archivo → *Conectar Google*
      (se abre el navegador para que autorices).
5. **Guardar ajustes.** Revisa la pestaña *Próximas reuniones*; cuando la lista te convenza,
   activa **Modo automático**.

Para que funcione siempre, deja la app abierta o minimizada. Si quieres que arranque sola:
en Windows, pon un acceso directo en la carpeta `shell:startup`; en Mac,
*Ajustes del Sistema → General → Ítems de inicio*.

## Cosas a tener en cuenta

- **El bot se ve.** Entra como un participante más con el nombre que elegiste, y las plataformas
  avisan que se está grabando. Lo más sano es decirle al equipo que mandas a tu "tomador de
  notas". Revisa también la política de tu empresa sobre grabar reuniones.
- **Sala de espera:** si nadie admite al bot, te llega un correo "⚠️ Sin resumen".
- **Empresas que bloquean invitados externos** (común en Teams y Meet corporativos) pueden
  impedir que el bot entre.
- El bot no habla por ti: si te preguntan algo, aparece en "Te mencionaron".
- Si la app está cerrada, no se mandan bots ni resúmenes; al volver a abrirla se pone al día
  con las reuniones que ya terminaron.

## Línea de comandos (opcional)

Para correrlo en un servidor sin pantalla: `python asistente.py login`, luego
`python asistente.py ejecutar` cada 5 minutos con cron. Usa `config.example.yaml` y
`.env.example` como plantillas (en la misma carpeta que `asistente.py`).
