# Bot de Telegram Base en Python

Proyecto base y ejecutable de un bot de Telegram pensado como punto de partida para un futuro sistema de alertas.

Está armado para que puedas:

- aprender la estructura sin complejidad innecesaria
- probar el bot localmente con polling
- extenderlo más adelante con consultas a APIs, lógica de monitoreo y alertas automáticas

## Tecnologías

- Python 3.11+
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- [python-dotenv](https://github.com/theskumar/python-dotenv)

## Funcionalidades actuales

- `/start`: mensaje de bienvenida
- `/help`: lista de comandos
- `/ping`: responde `pong`
- `/status`: indica que el bot está online
- `/echo <texto>`: devuelve el texto recibido
- comando desconocido: responde con un mensaje amable para usar `/help`

## Estructura del proyecto

```text
.
├── .env.example
├── .gitignore
├── README.md
├── main.py
├── requirements.txt
└── bot
    ├── __init__.py
    ├── application.py
    ├── config.py
    ├── error_handler.py
    └── handlers.py
```

## Cómo crear el bot con BotFather

1. Abrí Telegram y buscá `@BotFather`.
2. Iniciá el chat y ejecutá `/start`.
3. Ejecutá `/newbot`.
4. Elegí un nombre visible para tu bot.
5. Elegí un username único que termine en `bot`, por ejemplo `mi_alerta_bot`.
6. BotFather te va a devolver un token.
7. Guardá ese token porque lo vas a poner en tu archivo `.env`.

Opcional más adelante:

- `/setdescription` para una descripción
- `/setuserpic` para una foto
- `/setcommands` para definir comandos visibles en Telegram

## Cómo crear y activar un entorno virtual en macOS con zsh

Desde la carpeta del proyecto:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

Si no tenés `python3.11`, probá:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Cuando el entorno está activo, normalmente vas a ver `(.venv)` al principio de la línea de tu terminal.

## Cómo instalar dependencias

Con el entorno virtual activado:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## Cómo configurar el archivo .env

1. Copiá el archivo de ejemplo:

```bash
cp .env.example .env
```

2. Editá `.env` y reemplazá el valor de `TELEGRAM_BOT_TOKEN` por el token real de BotFather.

Ejemplo:

```env
TELEGRAM_BOT_TOKEN=123456789:ABCDEF_TU_TOKEN_REAL
LOG_LEVEL=INFO
```

## Cómo correr el bot

Con el entorno virtual activado y el `.env` configurado:

```bash
python main.py
```

Si todo está bien, vas a ver logs en consola indicando que el bot arrancó y está esperando mensajes.

## Cómo probarlo

1. Abrí Telegram.
2. Buscá tu bot por el username que elegiste.
3. Ejecutá estos comandos:
   - `/start`
   - `/help`
   - `/ping`
   - `/status`
   - `/echo hola mundo`
   - `/comando_que_no_existe`

## Qué hace cada archivo

- `main.py`: punto de entrada; configura logs, carga variables de entorno y levanta el bot
- `bot/config.py`: lee y valida la configuración desde `.env`
- `bot/application.py`: construye la aplicación de Telegram y registra handlers
- `bot/handlers.py`: contiene la lógica de los comandos
- `bot/error_handler.py`: centraliza el manejo de errores
- `.env.example`: ejemplo de variables de entorno
- `requirements.txt`: dependencias del proyecto
- `.gitignore`: evita subir archivos sensibles o temporales

## Comandos disponibles

### `/start`

Muestra un mensaje de bienvenida y confirma que el bot está listo.

### `/help`

Muestra la lista de comandos disponibles.

### `/ping`

Sirve para validar rápidamente que el bot responde.

### `/status`

Responde que el bot está online.

### `/echo <texto>`

Devuelve exactamente el texto que le envíes después del comando.

Ejemplo:

```text
/echo Este mensaje vuelve igual
```

## Logging y manejo de errores

- Los logs salen por consola.
- El nivel de log se controla con `LOG_LEVEL` en el `.env`.
- Si ocurre un error inesperado, el bot lo registra en consola e intenta responderle al usuario con un mensaje genérico.

## Subirlo a GitHub

Si querés dejarlo versionado desde el inicio:

```bash
git init
git add .
git commit -m "Base de bot de Telegram con polling"
git branch -M main
```

Después podés crear un repositorio en GitHub y vincularlo:

```bash
git remote add origin https://github.com/TU_USUARIO/TU_REPOSITORIO.git
git push -u origin main
```

## Próximo paso sugerido

Para convertir esta base en un bot de alertas deportivas, el siguiente crecimiento natural sería:

1. crear una carpeta `services/` para conectarte a una API de eventos deportivos
2. crear una carpeta `monitors/` para evaluar condiciones definidas por vos
3. agregar una tarea periódica que consulte la API cada cierto tiempo
4. separar una función `send_alert()` para centralizar el envío de mensajes por Telegram
5. guardar configuración de alertas en un archivo o base de datos liviana

Una evolución simple podría quedar así:

- `services/sports_api.py`: consulta partidos, cuotas o eventos
- `monitors/rules.py`: evalúa reglas como “si cuota > X” o “si empieza en menos de Y minutos”
- `bot/alerts.py`: envía alertas al chat correcto
- `bot/jobs.py`: programa chequeos automáticos cada N minutos

Con esa base, el bot ya no solo responde comandos: también observa, decide y te avisa solo.
