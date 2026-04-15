"""Local Python playground page for triggering a direct assistant call."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()
public_router = APIRouter()


def _render_page() -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Local Assistant Playground</title>
  <style>
    :root {{ color-scheme: dark; }}
    body {{ margin: 0; font-family: Inter, system-ui, sans-serif; background: #0b1020; color: #e5eefc; }}
    .wrap {{ max-width: 980px; margin: 0 auto; padding: 32px 20px 48px; }}
    .card {{ background: rgba(16, 24, 40, 0.92); border: 1px solid rgba(148, 163, 184, 0.22); border-radius: 18px; padding: 24px; box-shadow: 0 24px 64px rgba(0,0,0,0.35); }}
    h1 {{ margin: 0 0 8px; font-size: 28px; }}
    p {{ color: #a9b9d6; line-height: 1.5; }}
    label {{ display: block; margin-top: 16px; font-weight: 600; }}
    input, textarea {{ width: 100%; margin-top: 8px; box-sizing: border-box; border: 1px solid rgba(148, 163, 184, 0.28); border-radius: 14px; background: #0f172a; color: #e5eefc; padding: 12px 14px; font: inherit; }}
    textarea {{ min-height: 140px; resize: vertical; }}
    .row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    .actions {{ display: flex; gap: 12px; align-items: center; margin-top: 18px; flex-wrap: wrap; }}
    button {{ border: 0; border-radius: 12px; padding: 12px 18px; background: linear-gradient(135deg, #60a5fa, #8b5cf6); color: white; font-weight: 700; cursor: pointer; }}
    button:disabled {{ opacity: 0.65; cursor: not-allowed; }}
    pre {{ background: #020617; border: 1px solid rgba(148, 163, 184, 0.22); border-radius: 14px; padding: 14px; overflow: auto; white-space: pre-wrap; word-break: break-word; }}
    .hint {{ font-size: 13px; opacity: 0.86; }}
    .ok {{ color: #86efac; }}
    .error {{ color: #fca5a5; }}
    @media (max-width: 760px) {{ .row {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Local Assistant Playground</h1>
      <p>Trigger the existing assistant with the same configuration, while optionally overriding the first message and main system prompt.</p>
      <p class="hint">Leave the prompt fields empty to keep the assistant exactly as configured in Vapi.</p>

      <form id="call-form">
        <div class="row">
          <label>
            Assistant ID
            <input name="assistant_id" placeholder="Loaded from VAPI_ASSISTANT_ID" />
          </label>
          <label>
            Trigger Number
            <input name="phone_number" placeholder="+919876543210" required />
          </label>
        </div>

        <label>
          First Message Override
          <textarea name="first_message" placeholder="Optional. Leave blank to keep the Vapi assistant first message."></textarea>
        </label>

        <label>
          Main System Prompt Override
          <textarea name="system_prompt" placeholder="Optional. Leave blank to keep the Vapi assistant system prompt."></textarea>
        </label>

        <div class="actions">
          <button id="submit-btn" type="submit">Trigger Call</button>
          <span id="status" class="hint"></span>
        </div>
      </form>

      <h3>Result</h3>
      <pre id="output">Waiting for input…</pre>
    </div>
  </div>

  <script>
    const form = document.getElementById('call-form');
    const status = document.getElementById('status');
    const output = document.getElementById('output');
    const submitBtn = document.getElementById('submit-btn');

    form.addEventListener('submit', async (event) => {{
      event.preventDefault();
      status.textContent = 'Sending call request…';
      status.className = 'hint';
      submitBtn.disabled = true;

      const payload = {{
        assistant_id: form.assistant_id.value.trim(),
        phone_number: form.phone_number.value.trim(),
        first_message: form.first_message.value,
        system_prompt: form.system_prompt.value,
      }};

      try {{
        const response = await fetch('/api/direct-assistant-call', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(payload),
        }});

        const text = await response.text();
        output.textContent = text;

        if (!response.ok) {{
          status.textContent = 'Call request failed.';
          status.className = 'hint error';
        }} else {{
          status.textContent = 'Call request sent.';
          status.className = 'hint ok';
        }}
      }} catch (error) {{
        output.textContent = error instanceof Error ? error.message : String(error);
        status.textContent = 'Request failed.';
        status.className = 'hint error';
      }} finally {{
        submitBtn.disabled = false;
      }}
    }});
  </script>
</body>
</html>"""


@public_router.get("/playground", response_class=HTMLResponse)
async def playground() -> HTMLResponse:
    return HTMLResponse(_render_page())