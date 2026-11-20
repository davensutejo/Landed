// CTA teaser console: streams /api/chat and renders tool pills + the answer.
// The full workspace lives at /agent.

import { esc, renderMarkdown } from '../lib/markdown.js';
import { TOOL_LABEL, summarize, streamChat } from '../lib/agentStream.js';
import { renderHSQuiz, renderAskForm, detectLang } from '../lib/askWidgets.js';
import '../styles/ask.css';
import { isZh, L } from '../i18n.js';

const TOOL_ZH = { classify_hs: '识别 HS 编码', landed_cost: '计算到岸售价', price_check: '核算这个售价', compare_eu: '对比欧盟 27 国', compliance_flags: '检查合规要求', ask_seller: '整理需要补充的信息' };
const toolName = (n) => (isZh() ? TOOL_ZH[n] : TOOL_LABEL[n]) || n;

export { renderMarkdown };

export function initConsole() {
  const form = document.getElementById('cta-form');
  const input = document.getElementById('cta-email');
  const feedback = document.getElementById('cta-feedback');
  const log = document.getElementById('agent-console');
  const submitText = document.getElementById('cta-submit-text');
  const loader = document.getElementById('cta-inline-loader');
  if (!form || !input || !log) return;

  const history = [];
  let busy = false;

  document.querySelectorAll('[data-sample-prompt]').forEach((btn) => {
    btn.addEventListener('click', () => {
      input.value = btn.dataset.samplePrompt;
      input.focus();
    });
  });

  function add(cls, html) {
    const el = document.createElement('div');
    el.className = `console-msg ${cls}`;
    el.innerHTML = html;
    log.appendChild(el);
    log.hidden = false;
    log.scrollTo({ top: log.scrollHeight, behavior: 'smooth' }); // scroll the console, never the page
    return el;
  }

  form.addEventListener(
    'submit',
    async (e) => {
      e.preventDefault();
      const text = input.value.trim();
      if (busy) return;
      if (text.length < 2) {
        feedback.textContent = L('请描述你的产品与目标市场 · Describe the product and the target market.', '请先写下产品和目标市场。');
        return;
      }
      busy = true;
      feedback.textContent = '';
      input.value = '';
      history.push({ role: 'user', content: text });
      add('console-msg--user', `<p>${esc(text)}</p>`);
      const trail = add('console-msg--trail', '');
      if (submitText) submitText.textContent = '计算中…';
      if (loader) loader.hidden = false;
      const pending = {};
      const turn = { hs: null, ask: null, priced: false };
      const lang = detectLang(text);
      const followUp = (msg) => {
        input.value = msg;
        form.requestSubmit();
      };

      try {
        await streamChat(history, (ev) => {
          if (ev.type === 'tool_call' && ev.name === 'classify_hs') pending.classify_args = ev.args;
          if (ev.type === 'tool_result' && ev.name === 'classify_hs') turn.hs = { description: (pending.classify_args || {}).description || text, result: ev.result };
          if (ev.type === 'tool_result' && ev.name === 'ask_seller') turn.ask = ev.result;
          if (ev.type === 'tool_result' && ['landed_cost', 'price_check', 'compare_eu'].includes(ev.name) && ev.result && (ev.result.waterfall || ev.result.monte_carlo || ev.result.rows)) turn.priced = true;
          if (ev.type === 'tool_call') {
            const pill = document.createElement('details');
            pill.className = 'tool-pill';
            pill.innerHTML = `<summary><span class="tool-pill__dot"></span>${esc(toolName(ev.name))}<span class="tool-pill__sum">${L('running…', '进行中…')}</span></summary><pre>${esc(JSON.stringify(ev.args, null, 2))}</pre>`;
            trail.appendChild(pill);
            pending[ev.name] = pill;
          } else if (ev.type === 'tool_result') {
            const pill = pending[ev.name];
            if (pill) {
              pill.querySelector('.tool-pill__sum').textContent = summarize(ev.name, ev.result);
              pill.classList.add(ev.result && ev.result.status === 'abstain' ? 'is-abstain' : 'is-done');
            }
          } else if (ev.type === 'answer') {
            history.push({ role: 'assistant', content: ev.text });
            add('console-msg--agent', renderMarkdown(ev.text) + `<p><a href="/agent">${L('在完整工作台中继续分析 · Open the full workspace →', '在完整工作台中继续分析 →')}</a></p>`);
          } else if (ev.type === 'guardrail') {
            add('console-msg--warn', L(`<p>⚠ Guardrail: not found in any tool result or your message: <strong>${ev.unverified.map(esc).join(', ')}</strong>. Treat as unverified.</p>`, `<p>⚠ 护栏提示：以下内容在计算结果和你的消息里都找不到，请勿直接使用：<strong>${ev.unverified.map(esc).join('、')}</strong></p>`));
          } else if (ev.type === 'error') {
            add('console-msg--warn', `<p>${esc(ev.message)}</p>`);
          }
        });
        if (!trail.children.length) trail.remove();
        if (turn.ask && turn.ask.status === 'awaiting_seller') renderAskForm(add('console-msg--widget', ''), { ...turn.ask, lang, onSend: followUp });
        if (turn.hs && !turn.priced && ['ambiguous', 'needs_confirmation', 'resolved'].includes((turn.hs.result || {}).status)) renderHSQuiz(add('console-msg--widget', ''), { ...turn.hs, lang, onSend: followUp });
      } catch (err) {
        add('console-msg--warn', L(`<p>Agent unavailable (${esc(err.message)}). The worked example above is computed by the same engine.</p>`, `<p>助手暂时连不上（${esc(err.message)}）。上面的算例由同一套引擎计算，可以先看那里。</p>`));
      } finally {
        busy = false;
        if (submitText) submitText.textContent = '计算到岸价';
        if (loader) loader.hidden = true;
      }
    }
  );
}
