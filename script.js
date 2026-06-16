if (window.__emojiStudioInit) return [];
window.__emojiStudioInit = true;

/* ── 1. Build the picker and attach it to <body> ── */
const picker = document.createElement('div');
picker.id = 'emoji-overlay-picker';
picker.innerHTML = `
    <div id="eop-header">
        <span>Your emojis</span>
        <button id="eop-close" title="Close">✕</button>
    </div>
    <div id="eop-grid"></div>
    <div id="eop-empty">No emojis yet, ask me to make one!</div>
`;
document.body.appendChild(picker);

/* Tooltip element — also on body, fixed */
const tooltip = document.createElement('div');
tooltip.className = 'eop-tip';
document.body.appendChild(tooltip);

/* ── 2. Helpers ── */
window.__eopOpen = false;

function openPicker() {
    const btn = document.getElementById('emoji-pick-btn');
    if (!btn) return;
    const r = btn.getBoundingClientRect();
    const pickerW = 280;
    let left = r.right - pickerW;
    if (left < 8) left = 8;
    const bottom = window.innerHeight - r.top + 8;
    picker.style.left   = left + 'px';
    picker.style.bottom = bottom + 'px';
    picker.style.top    = 'auto';
    picker.classList.add('eop-open');
    window.__eopOpen = true;
}

function closePicker() {
    picker.classList.remove('eop-open');
    window.__eopOpen = false;
    tooltip.style.display = 'none';
}

window.__syncComposer = function() {
    const composer = document.getElementById('composer');
    const ta = document.querySelector('#hidden-txt textarea, #hidden-txt input');
    if (!composer || !ta) return;
    let value = '';
    composer.childNodes.forEach(node => {
        if (node.nodeType === Node.TEXT_NODE) {
            value += node.textContent;
        } else if (node.tagName === 'IMG') {
            value += '<emoji>' + (node.dataset.emojiName || '') + '</emoji>';
        } else {
            value += node.textContent || '';
        }
    });
    ta.value = value;
    ta.dispatchEvent(new Event('input', { bubbles: true }));
};

function insertEmoji(name, src) {
    const composer = document.getElementById('composer');
    if (!composer) return;
    composer.focus();
    const img = document.createElement('img');
    img.src = src;
    img.alt = '<emoji>' + name + '</emoji>';
    img.className = 'ei';
    img.dataset.emojiName = name;
    img.draggable = false;
    const sel = window.getSelection();
    if (sel && sel.rangeCount) {
        const range = sel.getRangeAt(0);
        if (composer.contains(range.commonAncestorContainer)) {
            range.deleteContents();
            range.insertNode(img);
            range.setStartAfter(img);
            range.collapse(true);
            sel.removeAllRanges();
            sel.addRange(range);
            closePicker();
            window.__syncComposer();
            return;
        }
    }
    composer.appendChild(img);
    closePicker();
    window.__syncComposer();
}

/* ── 3. Render picker grid from inventory ── */
window.__renderEmojiPicker = function(inventory) {
    const grid  = document.getElementById('eop-grid');
    const empty = document.getElementById('eop-empty');
    if (!grid || !empty) return;
    grid.innerHTML = '';
    const items = (inventory || []).filter(it => it.name && it.image_b64);
    if (items.length === 0) {
        grid.style.display = 'none';
        empty.style.display = 'block';
    } else {
        grid.style.display = 'grid';
        empty.style.display = 'none';
        items.forEach(it => {
            const btn = document.createElement('button');
            btn.className = 'eop-btn';
            btn.type = 'button';
            const img = document.createElement('img');
            img.src = 'data:image/png;base64,' + it.image_b64;
            img.alt = it.name;
            btn.appendChild(img);
            const label = it.name.slice(0, 28);
            btn.addEventListener('mouseenter', e => {
                tooltip.textContent = label;
                tooltip.style.display = 'block';
                const br = btn.getBoundingClientRect();
                tooltip.style.left = (br.left + br.width / 2 - tooltip.offsetWidth / 2) + 'px';
                tooltip.style.top  = (br.top - tooltip.offsetHeight - 6) + 'px';
            });
            btn.addEventListener('mouseleave', () => { tooltip.style.display = 'none'; });
            btn.addEventListener('click', e => {
                e.stopPropagation();
                tooltip.style.display = 'none';
                insertEmoji(it.name, img.src);
            });
            grid.appendChild(btn);
        });
    }
};

/* ── 4. Wire the toggle button (poll until it exists) ── */
function wireToggleBtn() {
    const btn = document.getElementById('emoji-pick-btn');
    if (!btn) { setTimeout(wireToggleBtn, 200); return; }

    /* Fix icon centering: the button itself and its Gradio wrapper div */
    btn.style.display = 'flex';
    btn.style.alignItems = 'center';
    btn.style.justifyContent = 'center';
    btn.style.lineHeight = '1';
    if (btn.parentElement) {
        btn.parentElement.style.display = 'flex';
        btn.parentElement.style.alignItems = 'center';
        btn.parentElement.style.justifyContent = 'center';
        btn.parentElement.style.padding = '0';
    }

    btn.addEventListener('click', e => {
        e.stopPropagation();
        if (window.__eopOpen) { closePicker(); } else { openPicker(); }
    });
}
wireToggleBtn();

/* 4b. Watch picker-sync container for inventory updates */
function watchPickerSync() {
    const container = document.getElementById('picker-sync');
    if (!container) { setTimeout(watchPickerSync, 200); return; }
    function apply() {
        const target = container.querySelector('#picker-sync-data');
        if (!target) return;
        try {
            const raw = target.getAttribute('data-inv').replace(/&quot;/g, '"');
            const inv = JSON.parse(raw);
            if (window.__renderEmojiPicker) window.__renderEmojiPicker(inv);
        } catch(e) { console.error('picker sync parse error', e); }
    }
    const observer = new MutationObserver(apply);
    observer.observe(container, { childList: true, subtree: true });
    apply();
}
watchPickerSync();

function findDirectChild(el, ancestor) {
    while (el && el.parentElement !== ancestor) {
        el = el.parentElement;
    }
    return el;
}

function fixTopRowLayout() {
    const composer = document.getElementById('composer');
    const emojiBtn = document.getElementById('emoji-pick-btn');
    const topRow   = document.getElementById('top-row');
    if (!composer || !emojiBtn || !topRow) { setTimeout(fixTopRowLayout, 200); return; }

    const composerWrap = findDirectChild(composer, topRow);
    const emojiWrap    = findDirectChild(emojiBtn, topRow);

    if (composerWrap) {
        composerWrap.style.flex     = '1 1 auto';
        composerWrap.style.width    = 'auto';
        composerWrap.style.minWidth = '0';
    }
    if (emojiWrap) {
        emojiWrap.style.flex           = '0 0 44px';
        emojiWrap.style.width          = '44px';
        emojiWrap.style.display        = 'flex';
        emojiWrap.style.alignItems     = 'center';
        emojiWrap.style.justifyContent = 'center';
        emojiWrap.style.margin  = '0';
        emojiWrap.style.padding = '0';
    }
}
fixTopRowLayout();

/* ── 5. Close picker on outside click ── */
document.addEventListener('click', e => {
    if (!window.__eopOpen) return;
    const btn = document.getElementById('emoji-pick-btn');
    if (picker.contains(e.target)) return;
    if (btn && btn.contains(e.target)) return;
    closePicker();
}, true);

/* ── 6. Close picker button ── */
document.addEventListener('click', e => {
    if (e.target && e.target.id === 'eop-close') closePicker();
});

/* ── 7. Composer: sync on input, Enter to send ── */
function wireComposer() {
    const composer = document.getElementById('composer');
    if (!composer) { setTimeout(wireComposer, 200); return; }
    composer.addEventListener('input', window.__syncComposer);
    composer.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            window.__syncComposer();
            const send = document.getElementById('send-btn');
            if (send) {
                send.click();
                setTimeout(() => {
                    composer.innerHTML = '';
                    window.__syncComposer();
                }, 60);
            }
        }
    });
    composer.addEventListener('paste', e => {
        e.preventDefault();
        const text = (e.clipboardData || window.clipboardData).getData('text');
        document.execCommand('insertText', false, text);
    });
}
wireComposer();

/* ── 8. Reposition picker on window resize/scroll ── */
window.addEventListener('resize', () => { if (window.__eopOpen) openPicker(); });
window.addEventListener('scroll', () => { if (window.__eopOpen) openPicker(); }, true);

/* ── 9. Open and close info overlay ── */
function wireInfoOverlay() {
    const btn = document.getElementById('info-btn');
    const overlay = document.getElementById('info-overlay');
    const close = document.getElementById('info-close');
    if (!btn || !overlay || !close) { setTimeout(wireInfoOverlay, 200); return; }
    btn.addEventListener('click', () => overlay.classList.add('open'));
    close.addEventListener('click', () => overlay.classList.remove('open'));
}
wireInfoOverlay();

/* ── Chat scroll and scrollbar management ── */
function setupChatScroll() {
    const chatDisplay = document.getElementById('chat-display');
    if (!chatDisplay) { setTimeout(setupChatScroll, 200); return; }

    function scrollToBottom() {
        const wrap = document.getElementById('chat-scroll-wrap');
        if (!wrap) return;
        wrap.scrollTop = wrap.scrollHeight;
    }

    const observer = new MutationObserver(() => {
        requestAnimationFrame(() => requestAnimationFrame(scrollToBottom));
    });

    observer.observe(chatDisplay, { childList: true, subtree: true });
    window.addEventListener('resize', scrollToBottom);
}
setupChatScroll();

const observer = new MutationObserver(() => {
    document.querySelectorAll('.progress-text').forEach(el => {
        el.style.setProperty('display', 'none', 'important');
    });
});
observer.observe(document.body, { childList: true, subtree: true });