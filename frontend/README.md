# VoiceForge Frontend

React + Vite dashboard for the VoiceForge backend pipeline.

## Setup

```bash
npm install
cp .env.example .env
```

## Run

```bash
npm run dev
```

By default, Vite proxies `/api` and `/health` to `VITE_PROXY_TARGET` (default: `http://127.0.0.1:8557`).
If you want to bypass proxy and call backend directly from browser, set `VITE_API_BASE_URL`.

Set `VITE_VAPI_PUBLIC_KEY` for browser voice mode (`Talk In Browser`) in the dashboard.

Notes:
- `Phone Call` mode keeps outbound phone dialing.
- `Talk In Browser` mode starts a direct browser voice session with the bot.
- `Industry` and `Use Case` now use dependent dropdowns from predefined mapping.
- `/sessions` shows session-wise status and transcript/messages dashboard.
- Use HTTPS in production for consistent microphone permission behavior.
