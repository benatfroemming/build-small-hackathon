# ============================================================
# Helpers
# ============================================================
import io, base64, re, json, os
from PIL import Image
from rembg import remove
from pathlib import Path
from huggingface_hub import InferenceClient

EMOJI_TAG_PATTERN = re.compile(r"<emoji>(.*?)</emoji>", re.DOTALL)
THINK_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL)
TOOL_CALL_PATTERN = re.compile(r"<tool_call>\s*(.+?)\s*</tool_call>", re.DOTALL)

CUSTOM_CSS = Path("style.css").read_text()
PAGE_JS_BODY = Path("script.js").read_text()
PAGE_JS = f"() => {{\n{PAGE_JS_BODY}\n}}"
INFO_MD = Path("info.md").read_text()

HF_TOKEN = os.environ.get("HF_TOKEN")
client = InferenceClient(token=HF_TOKEN)

QWEN_MODEL = "Qwen/Qwen3-8B"
FLUX_MODEL = "black-forest-labs/FLUX.1-schnell"


def generate_emoji_image(description: str) -> Image.Image:
    prompt = (
        "Apple iPhone emoji style, clean flat vector emoji illustration, "
        "single subject only, large subject filling 80-90% of the frame, "
        "tight crop, minimal padding, centered composition, "
        "no extra background elements, no text, no border, "
        "white background, high contrast, emoji-sized readability: "
        f"{description}"
    )
    image = client.text_to_image(
        prompt=prompt,
        model=FLUX_MODEL,
        width=512,
        height=512,
    )
    # client.text_to_image returns a PIL Image directly
    image = image.convert("RGBA")
    image = remove(image)
    return image


def image_to_b64(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def render_emojis(text: str, inventory: list) -> str:
    emoji_map = {
        item["name"]: item["image_b64"]
        for item in inventory
        if "name" in item and "image_b64" in item
    }
    def replace(match):
        name = match.group(1).strip()
        if name in emoji_map:
            b64 = emoji_map[name]
            return (
                f'<img src="data:image/png;base64,{b64}" '
                f'style="display:inline;height:1.4em;width:1.4em;'
                f'vertical-align:-0.3em;margin:0 0.1em;border-radius:0;border:none;" '
                f'alt="{name}"/>'
            )
        return ""
    result = EMOJI_TAG_PATTERN.sub(replace, text)
    result = re.sub(r"[ \t]+", " ", result).strip()
    return result


# ============================================================
# Tool schema
# ============================================================
GENERATE_EMOJI_TOOL = {
    "type": "function",
    "function": {
        "name": "generate_emoji",
        "description": (
            "Generates a brand-new emoji-style image. "
            "Call this when the user asks for a new emoji, sticker, or icon. "
            "Provide a short unique snake_case name and a visual description for image generation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Short unique snake_case identifier, e.g. 'pizza_slice' or 'happy_cat'",
                },
                "description": {
                    "type": "string",
                    "description": "Visual description used to generate the image, e.g. 'a steaming pizza slice with melted cheese'",
                },
            },
            "required": ["name", "description"],
        },
    },
}


# ============================================================
# System prompt
# ============================================================
BASE_SYSTEM_PROMPT = """\
You are a helpful assistant in a chat app that supports custom emojis.

Custom emojis are inserted with <emoji>name</emoji> syntax. When you use a \
registered emoji name inside those tags it renders as an image.

RULES:
- DEFAULT: use NO custom emoji. This is the default for every message, including greetings, \
  small talk, and generic replies.
- Do NOT use standard Unicode emoji characters at the same time as custom emojis <emoji>name</emoji>.
- STRICT MATCH ONLY: insert a custom emoji ONLY if the user's message explicitly expresses or describes \
  the exact situation in that emoji's "meaning" (e.g. the user states they feel sad, stressed, down, etc. \
  for a "cheer up when sad" emoji). A neutral or generic message (e.g. "hi", "hello", "how are you", \
  "ok", "thanks") NEVER qualifies, even if the emoji's meaning is broadly positive or cheerful.
- If you are unsure whether a message qualifies, do NOT use the emoji.
- Only use names from the "Registered emojis" list. Never guess or invent names.
- Never responds with a single emoji alone without additional text.
- Never refer to or describe an emoji in text (e.g. "here's a", "have this emoji"). \
  Insert emoji only as a decorative inline addition to add meaning.
- When the user asks for a new emoji/sticker/icon, call the generate_emoji tool \
  with a fitting name and description. Do not ask the user for the name or description.
- After the tool call your job is done — the system handles the follow-up flow.
"""

def build_system_prompt(inventory: list) -> str:
    registered = [it for it in inventory if "name" in it and "image_b64" in it and it.get("meaning")]
    if not registered:
        emoji_section = "(No custom emojis registered yet.)"
    else:
        lines = [
            f'- name: "{it["name"]}" | meaning: {it["meaning"]}'
            for it in registered
        ]
        emoji_section = "Registered emojis:\n" + "\n".join(lines)
    return BASE_SYSTEM_PROMPT + "\n" + emoji_section


# ============================================================
# LLM helpers
# ============================================================
def strip_think(text: str) -> str:
    return THINK_PATTERN.sub("", text).strip()


def run_qwen(messages, tools=None, max_new_tokens=512):
    # Build the chat_completion call; tools forwarded if provided
    kwargs = dict(
        model=QWEN_MODEL,
        messages=messages,
        max_tokens=max_new_tokens,
        temperature=0.2,
        top_p=0.9,
    )
    if tools:
        kwargs["tools"] = tools

    response = client.chat_completion(**kwargs)
    msg = response.choices[0].message

    # If the model returned a native tool_call (OpenAI-style), re-serialise
    # it as the <tool_call>…</tool_call> format the rest of the code expects.
    if msg.tool_calls:
        tc = msg.tool_calls[0]
        args = tc.function.arguments
        if isinstance(args, dict):
            args = json.dumps(args)
        payload = json.dumps({"name": tc.function.name, "arguments": json.loads(args)})
        return f"<tool_call>{payload}</tool_call>"

    return (msg.content or "").strip()


def _extract_tool_call(reply: str):
    match = TOOL_CALL_PATTERN.search(reply)
    if not match:
        return None, {}
    try:
        call = json.loads(match.group(1))
        return call.get("name"), call.get("arguments", {}) or {}
    except json.JSONDecodeError:
        return None, {}


def _strip_tool_artifacts(text: str) -> str:
    text = TOOL_CALL_PATTERN.sub("", text)
    text = re.sub(r"</?tool_call>", "", text)
    text = re.sub(
        r'\{\s*"name"\s*:\s*"generate_emoji".*\}\s*$', "", text, flags=re.DOTALL,
    )
    return text.strip()


# ============================================================
# Chat logic
# ============================================================
ASKING_MSG = "What should this emoji mean, and when would you use it? (type 'cancel' to abort)"


def chat_turn(message: str, llm_history: list, inventory: list, pending_emoji: dict | None):
    system_prompt = build_system_prompt(inventory)

    if pending_emoji is not None:
        meaning = message.strip()
        
        # abort emoji generation
        if meaning.lower().strip() == "cancel":
            abort_raw = "Got it, emoji generation cancelled. No emoji was saved."
            assistant_messages = [{"role": "assistant", "content": abort_raw, "raw": abort_raw}]
            updated_llm_history = llm_history + [
                {"role": "user",      "content": message},
                {"role": "assistant", "content": abort_raw},
            ]
            return assistant_messages, None, inventory, updated_llm_history, None
        
        completed_entry = {**pending_emoji, "meaning": meaning}
        updated_inventory = inventory + [completed_entry]

        emoji_tag = f"<emoji>{pending_emoji['name']}</emoji>"
        confirm_raw = f"Got it! Your new emoji {emoji_tag} has been saved. You can now use it in any message!"

        confirm_display = render_emojis(confirm_raw, updated_inventory)

        assistant_messages = [{"role": "assistant", "content": confirm_display, "raw": confirm_raw}]
        updated_llm_history = llm_history + [
            {"role": "user",      "content": message},
            {"role": "assistant", "content": confirm_raw},
        ]
        return assistant_messages, None, updated_inventory, updated_llm_history, None

    messages = [{"role": "system", "content": system_prompt}] + llm_history
    messages.append({"role": "user", "content": message})

    reply = strip_think(run_qwen(messages, tools=[GENERATE_EMOJI_TOOL]))
    fn_name, fn_args = _extract_tool_call(reply)

    if fn_name == "generate_emoji":
        name        = (fn_args.get("name") or "").strip()
        description = (fn_args.get("description") or "").strip()
        if not name:
            name = re.sub(r"[^a-z0-9]+", "_", description.lower()).strip("_")[:32]

        print(f"[Tool] generate_emoji  name={name!r}  desc={description!r}")
        image    = generate_emoji_image(description)
        b64      = image_to_b64(image)

        pending = {"name": name, "description": description, "image_b64": b64}

        ask_display = render_emojis(ASKING_MSG, inventory)
        assistant_messages = [
            {"role": "assistant", "content": {"image_b64": b64}},
            {"role": "assistant", "content": ask_display, "raw": ASKING_MSG},
        ]

        updated_llm_history = llm_history + [
            {"role": "user",      "content": message},
            {"role": "assistant", "content": f"[Generated emoji '{name}'. Awaiting user description.]"},
        ]
        return assistant_messages, image, inventory, updated_llm_history, pending

    reply = _strip_tool_artifacts(reply) or "Got it!"
    reply_display = render_emojis(reply, inventory)
    assistant_messages = [{"role": "assistant", "content": reply_display, "raw": reply}]

    updated_llm_history = llm_history + [
        {"role": "user",      "content": message},
        {"role": "assistant", "content": reply},
    ]
    return assistant_messages, None, inventory, updated_llm_history, None


# ============================================================
# Gradio UI
# ============================================================
import gradio as gr

# ── Chat HTML renderer ─────────────────────────────────────────────────────
def render_chat_html(display_history: list) -> str:
    rows = []
    for msg in display_history:
        role    = msg["role"]
        content = msg["content"]
        is_sys  = msg.get("system_note", False)
        is_typing = msg.get("typing", False)

        if is_typing:
            rows.append(
                '<div class="brow b">'
                '<div class="bbl b typing">'
                '<span class="dot"></span><span class="dot"></span><span class="dot"></span>'
                '</div></div>'
            )
        elif is_sys:
            rows.append(
                '<div class="brow sys-wrap">'
                f'<div class="bbl sys">{content}</div></div>'
            )
        elif isinstance(content, dict) and "image_b64" in content:
            rows.append(
                '<div class="brow b">'
                f'<div class="bbl b">'
                f'<img class="gi" src="data:image/png;base64,{content["image_b64"]}" alt="generated emoji"/>'
                f'</div></div>'
            )
        else:
            css = "u" if role == "user" else "b"
            rows.append(
                f'<div class="brow {css}">'
                f'<div class="bbl {css}">{content}</div></div>'
            )

    if not rows:
        body = (
            '<div style="flex:1;display:flex;align-items:center;justify-content:center;">'
            '<span style="color:#2e3548;font-size:13px;">Chat or ask for a new emoji!</span>'
            '</div>'
        )
    else:
        body = "".join(rows)

    return f'<div id="chat-scroll-wrap">{body}</div>'

# ── Emoji picker inventory sync ────────────────────────────────────────────
def render_picker_sync(inventory: list) -> str:
    safe_json = json.dumps(inventory).replace('"', "&quot;")
    return f'<div id="picker-sync-data" data-inv="{safe_json}"></div>'

# ── Gradio event handlers ──────────────────────────────────────────────────
def _submit_user(message, display_history, llm_history, inventory, pending_emoji):
    msg = str(message or "").strip()
    if not msg:
        return render_chat_html(display_history), display_history, llm_history, inventory, pending_emoji, ""
    user_display = render_emojis(msg, inventory)
    new_display  = display_history + [
        {"role": "user", "content": user_display},
        {"role": "assistant", "content": "...", "typing": True},
    ]
    return render_chat_html(new_display), new_display, llm_history, inventory, pending_emoji, msg


def _submit_bot(message, display_history, llm_history, inventory, pending_emoji):
    display_history = [m for m in display_history if not m.get("typing")]
    msg = str(message or "").strip()
    if not msg:
        return (
            render_chat_html(display_history), display_history,
            llm_history, inventory, pending_emoji,
            render_picker_sync(inventory),
        )
    asst_msgs, new_image, updated_inv, updated_hist, new_pending = chat_turn(
        msg, llm_history, inventory, pending_emoji
    )
    new_display = list(display_history)
    if new_image is not None:
        b64 = image_to_b64(new_image)
        new_display.append({"role": "assistant", "content": {"image_b64": b64}})
    for am in asst_msgs:
        if isinstance(am["content"], str):
            new_display.append({"role": "assistant", "content": am["content"]})
    return (
        render_chat_html(new_display), new_display,
        updated_hist, updated_inv, new_pending,
        render_picker_sync(updated_inv),
    )


def _clear_chat(inventory):
    return render_chat_html([]), [], [], render_picker_sync(inventory), None


# ── Build UI ───────────────────────────────────────────────────────────────
with gr.Blocks(css=CUSTOM_CSS, title="Emoji Studio", analytics_enabled=False) as demo:

    # States
    inventory_state       = gr.State([])
    llm_history_state     = gr.State([])
    display_history_state = gr.State([])
    pending_emoji_state   = gr.State(None)
    msg_state             = gr.State("")

    # ── App shell ──
    with gr.Column(elem_id="app-shell"):

        # Header
        gr.HTML("""
            <div id="app-header">
                <div class="logo">🤗</div>
                <div>
                    <div class="title">Emoji Studio</div>
                    <div class="sub">Create your own emojies, give them meaning, and use them with your chatbot.</div>
                </div>
                <button type="button" id="info-btn" class="icon-btn" title="About" aria-label="Open info">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="12" y1="16" x2="12" y2="12"></line>
                        <line x1="12" y1="8" x2="12.01" y2="8"></line>
                    </svg>
                </button>
            </div>
        """)

        with gr.Column(elem_id="info-overlay"):
            gr.HTML('<button type="button" id="info-close" aria-label="Close">✕</button>')
            gr.Markdown(INFO_MD, elem_id="info-content")

        # Chat display
        chat_html = gr.HTML(render_chat_html([]), elem_id="chat-display")

        # Hidden inventory sync (updates picker JS-side)
        picker_sync = gr.HTML(render_picker_sync([]), elem_id="picker-sync")

        # Input zone
        with gr.Row(elem_id="input-zone"):
            with gr.Row(elem_id="composer-wrap"):
                gr.HTML("""
                <div id="top-row">
                    <div id="composer"
                        contenteditable="true"
                        data-ph="Message… (Shift+Enter for new line)"
                        spellcheck="true"
                        role="textbox"
                        aria-multiline="true"
                        aria-label="Message composer"></div>
                    <button type="button"
                            id="emoji-pick-btn"
                            class="icon-btn"
                            title="Custom emojis"
                            aria-label="Open emoji picker"
                            aria-haspopup="true">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <circle cx="12" cy="12" r="10"></circle>
                            <path d="M8 14s1.5 2 4 2 4-2 4-2"></path>
                            <line x1="9" y1="9" x2="9" y2="9.01"></line>
                            <line x1="15" y1="9" x2="15" y2="9.01"></line>
                        </svg>
                    </button>
                </div>
                """)
                txt = gr.Textbox(
                    value="", show_label=False, container=False,
                    lines=1, elem_id="hidden-txt", visible=False,
                )

            # Send/Clear row below, 50/50
            with gr.Row(elem_id="bottom-btn-row"):
                send_btn  = gr.Button("Send", elem_id="send-btn", elem_classes=["icon-btn"])
                clear_btn = gr.Button("Clear", elem_id="clear-btn",  elem_classes=["icon-btn"])
                
        gr.HTML("""
        <div id="app-footer">
            Built for the Hugging Face Build Small Hackathon 🤗
        </div>
        """)

    # ── Event wiring ──
    SEND_IN  = [txt, display_history_state, llm_history_state, inventory_state, pending_emoji_state]
    USER_OUT = [chat_html, display_history_state, llm_history_state, inventory_state, pending_emoji_state, msg_state]
    BOT_IN   = [msg_state, display_history_state, llm_history_state, inventory_state, pending_emoji_state]
    BOT_OUT  = [chat_html, display_history_state, llm_history_state, inventory_state, pending_emoji_state, picker_sync]

    for trigger in [send_btn.click, txt.submit]:
        trigger(
            _submit_user,
            inputs=SEND_IN,
            outputs=USER_OUT,
            show_progress="hidden",
        ).then(
            lambda: "",
            outputs=[txt],
            show_progress="hidden",
            js=(
                "() => {"
                "  const c = document.getElementById('composer');"
                "  if (c) { c.innerHTML = ''; c.contentEditable = 'false'; }"
                "  const send = document.getElementById('send-btn');"
                "  const clear = document.getElementById('clear-btn');"
                "  const emoji = document.getElementById('emoji-pick-btn');"
                "  if (send) send.disabled = true;"
                "  if (clear) clear.disabled = true;"
                "  if (emoji) emoji.disabled = true;"
                "  document.getElementById('input-zone').classList.add('disabled');"
                "  if (window.__syncComposer) window.__syncComposer();"
                "  return '';"
                "}"
            ),
        ).then(
            _submit_bot,
            inputs=BOT_IN,
            outputs=BOT_OUT,
            show_progress="hidden",
        ).then(
            None, None, None,
            show_progress="hidden",
            js=(
                "() => {"
                "  const c = document.getElementById('composer');"
                "  if (c) { c.contentEditable = 'true'; c.focus(); }"
                "  const send = document.getElementById('send-btn');"
                "  const clear = document.getElementById('clear-btn');"
                "  const emoji = document.getElementById('emoji-pick-btn');"
                "  if (send) send.disabled = false;"
                "  if (clear) clear.disabled = false;"
                "  if (emoji) emoji.disabled = false;"
                "  document.getElementById('input-zone').classList.remove('disabled');"
                "  return [];"
                "}"
            ),
        )

    clear_btn.click(
        _clear_chat,
        inputs=[inventory_state],
        outputs=[chat_html, display_history_state, llm_history_state, picker_sync, pending_emoji_state],
        show_progress="hidden",
    ).then(
        None, None, None,
        show_progress="hidden",
        js="""
        () => {
            const target = document.querySelector('#picker-sync #picker-sync-data');
            if (target && window.__renderEmojiPicker) {
                try {
                    const raw = target.getAttribute('data-inv').replace(/&quot;/g, '"');
                    const inv = JSON.parse(raw);
                    window.__renderEmojiPicker(inv);
                } catch(e) { console.error(e); }
            }
            return [];
        }
        """
    )

    demo.load(None, None, None, js=PAGE_JS)

demo.launch()