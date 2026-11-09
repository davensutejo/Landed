// Interactive "ask, don't guess" widgets rendered inside the chat.
//  - HS quiz: yes / no / not sure buttons walk the deterministic classifier
//    (/api/classify) instantly, then a Confirm button sends one message to the agent.
//  - Ask form: structured inputs for missing cost / weight / market / margin.

import { esc } from './markdown.js';
import { EU } from './markets.js';
import { postJSON } from './agentStream.js';

export function detectLang(text = '') {
  const cjk = (text.match(/[一-鿿]/g) || []).length;
  const latin = (text.match(/[A-Za-z]/g) || []).length;
  return cjk && cjk * 2 >= latin * 0.5 ? 'zh' : 'en';
}

const T = {
  en: {
    hsTitle: 'Quick check to pin the HS code',
    remaining: (n) => `${n} candidate code${n === 1 ? '' : 's'} left`,
    bits: (b) => `this answer narrows it by ${b} bits`,
    yes: 'Yes',
    no: 'No',
    unsure: 'Not sure',
    confirm: (hs) => `✓ Confirm HS ${hs}`,
    wrong: 'That’s not my product',
    resolvedLead: 'Every deciding attribute is answered. One code fits:',
    noneLead: 'No code in Landed’s verified category fits these answers.',
    sendNone: 'Tell the agent',
    formTitle: 'A few details to price this',
    send: 'Continue →',
    done: 'Sent',
    yesWord: 'yes',
    noWord: 'no'
  },
  zh: {
    hsTitle: '快速确认 HS 编码',
    remaining: (n) => `剩余 ${n} 个候选编码`,
    bits: (b) => `本题可减少 ${b} bit 不确定性`,
    yes: '是',
    no: '否',
    unsure: '不确定',
    confirm: (hs) => `✓ 确认 HS ${hs}`,
    wrong: '这不是我的产品',
    resolvedLead: '关键属性已全部确认，唯一匹配的编码：',
    noneLead: '在已验证的品类中没有匹配的编码。',
    sendNone: '告诉 Agent',
    formTitle: '补充几项信息即可定价',
    send: '继续 →',
    done: '已发送',
    yesWord: '是',
    noWord: '否'
  }
};

const ATTR_Q_ZH = {
  has_electric_motor: '产品是否带有驱动刀片的电机？',
  motor_self_contained: '电机是否内置在产品本身（而不是需要外接底座或厨房机）？',
  has_heating_element: '产品是否有加热功能（例如煮汤）？',
  domestic_use: '是否为家用设计（而非商用/工业食品加工）？',
  is_accessory_only: '是否只是单独销售的杯子/杯身/盖子，不含电机？'
};
const ATTR_NAME = {
  en: {
    has_electric_motor: 'electric motor',
    motor_self_contained: 'motor built into the product',
    has_heating_element: 'heating function',
    domestic_use: 'household use',
    is_accessory_only: 'accessory only (no motor)'
  },
  zh: {
    has_electric_motor: '带电机',
    motor_self_contained: '电机内置',
    has_heating_element: '加热功能',
    domestic_use: '家用',
    is_accessory_only: '仅为配件（无电机）'
  }
};

function lockWidget(root, chosenBtn) {
  root.querySelectorAll('button, input, select').forEach((b) => (b.disabled = true));
  if (chosenBtn) chosenBtn.classList.add('is-chosen');
  root.classList.add('is-locked');
}

// ------------------------------------------------------------ HS quiz
export function renderHSQuiz(host, { description, result, lang = 'en', onUpdate, onSend }) {
  const t = T[lang];
  const root = document.createElement('div');
  root.className = 'ask-card ask-card--hs';
  host.appendChild(root);
  let known = { ...(result.known_attributes || {}) };
  let current = result;

  const facts = () =>
    Object.entries(known)
      .map(([k, v]) => `${ATTR_NAME[lang][k] || k}: ${v ? t.yesWord : t.noWord}`)
      .join(lang === 'zh' ? '；' : '; ');

  function draw() {
    const r = current;
    const cands = r.candidates || [];
    const chips = cands
      .map((c, i) => `<li class="ask-cand ${r.status === 'resolved' && i === 0 ? 'is-win' : ''}"><b>${esc(c.hs)}</b> <span>${esc(c.title)}</span></li>`)
      .join('');
    let body = '';
    if (r.status === 'ambiguous' || r.status === 'needs_confirmation') {
      const q = r.next_question;
      const qText = lang === 'zh' ? ATTR_Q_ZH[q.attribute] || q.question : q.question;
      body = `<p class="ask-q">${esc(qText)}</p>
        <div class="ask-btns">
          <button type="button" class="ask-btn" data-a="yes">${t.yes}</button>
          <button type="button" class="ask-btn" data-a="no">${t.no}</button>
          <button type="button" class="ask-btn ask-btn--ghost" data-a="unsure">${t.unsure}</button>
        </div>`;
    } else if (r.status === 'resolved') {
      const hs = cands[0].hs;
      body = `<p class="ask-q">${t.resolvedLead}</p>
        <p class="ask-why">${esc(cands[0].reasoning)}</p>
        <div class="ask-btns">
          <button type="button" class="ask-btn ask-btn--primary" data-a="confirm">${t.confirm(esc(hs))}</button>
          <button type="button" class="ask-btn ask-btn--ghost" data-a="wrong">${t.wrong}</button>
        </div>`;
    } else {
      body = `<p class="ask-q">${t.noneLead}</p><div class="ask-btns"><button type="button" class="ask-btn" data-a="none">${t.sendNone}</button></div>`;
    }
    root.innerHTML = `<div class="ask-head"><span class="ask-title">${t.hsTitle}</span><span class="ask-meta">${t.remaining(cands.length)}</span></div>
      ${Object.keys(known).length ? `<p class="ask-facts">${esc(facts())}</p>` : ''}
      <ul class="ask-cands">${chips}</ul>${body}`;

    root.querySelectorAll('[data-a]').forEach((b) =>
      b.addEventListener('click', async () => {
        const a = b.dataset.a;
        if (a === 'yes' || a === 'no') {
          known = { ...known, [current.next_question.attribute]: a === 'yes' };
          root.classList.add('is-busy');
          try {
            current = await postJSON('/api/classify', { description, attributes: known });
            if (onUpdate) onUpdate(current);
          } finally {
            root.classList.remove('is-busy');
          }
          draw();
        } else if (a === 'confirm') {
          const hs = current.candidates[0].hs;
          lockWidget(root, b);
          onSend(lang === 'zh' ? `确认 HS ${hs}。产品信息：${facts()}。` : `Confirmed HS ${hs}. Product facts: ${facts()}.`);
        } else if (a === 'unsure') {
          const q = current.next_question;
          const open = (current.candidates || []).map((c) => c.hs).join(' / ');
          lockWidget(root, b);
          onSend(
            lang === 'zh'
              ? `我不确定：${ATTR_Q_ZH[q.attribute] || q.question} 目前仍可能的编码：${open}。已知：${facts() || '无'}。`
              : `I'm not sure: ${q.question} Codes still open: ${open}. Known so far: ${facts() || 'nothing'}.`
          );
        } else if (a === 'wrong') {
          lockWidget(root, b);
          onSend(lang === 'zh' ? `建议的 HS ${current.candidates[0].hs} 不符合我的产品。已知：${facts()}。` : `HS ${current.candidates[0].hs} doesn't describe my product. Known so far: ${facts()}.`);
        } else if (a === 'none') {
          lockWidget(root, b);
          onSend(lang === 'zh' ? `没有匹配的编码。已知：${facts()}。` : `No code matched. Known so far: ${facts()}.`);
        }
      })
    );
  }
  draw();
  return root;
}

// ------------------------------------------------------------ ask form
const FIELD_DEF = {
  cogs_cny: { en: 'Unit cost (CNY)', zh: '单位成本（元）', type: 'number', step: '0.01', min: '0.01', ph: '38' },
  weight_kg: { en: 'Shipping weight (kg)', zh: '发货重量（kg）', type: 'number', step: '0.01', min: '0.01', ph: '0.6' },
  market: { en: 'Market', zh: '目标市场', type: 'select', options: [...EU.map((c) => [c[0], c[1], c[2]]), ['US', 'United States', '美国']] },
  target_margin: { en: 'Target margin (%)', zh: '目标毛利率（%）', type: 'number', step: '1', min: '1', max: '70', ph: '25', pct: true },
  item_categories: { en: 'Tariff categories per parcel', zh: '每个包裹的税则类别数', type: 'number', step: '1', min: '1', max: '6', ph: '1', hint: { en: 'blender + spare cup = 2', zh: '例：搅拌杯 + 备用杯 = 2' } },
  battery_builtin: { en: 'Built-in lithium battery?', zh: '是否内置锂电池？', type: 'bool' },
  food_contact: { en: 'Touches food or drink?', zh: '是否接触食品或饮料？', type: 'bool' }
};

export function renderAskForm(host, { fields, prefill = {}, note = '', lang = 'en', onSend }) {
  const t = T[lang];
  const root = document.createElement('form');
  root.className = 'ask-card ask-card--form';
  root.noValidate = true;
  const rows = fields
    .filter((f) => FIELD_DEF[f])
    .map((f) => {
      const d = FIELD_DEF[f];
      const label = d[lang];
      let v = prefill[f];
      if (d.pct && v != null && v < 1) v = Math.round(v * 100);
      let input;
      if (d.type === 'select') {
        input = `<select name="${f}">${d.options.map(([val, en, zh]) => `<option value="${val}" ${v === val ? 'selected' : ''}>${lang === 'zh' ? zh : en}</option>`).join('')}</select>`;
      } else if (d.type === 'bool') {
        input = `<div class="ask-seg"><label><input type="radio" name="${f}" value="yes" ${v === true ? 'checked' : ''}/> ${t.yes}</label><label><input type="radio" name="${f}" value="no" ${v === false ? 'checked' : ''}/> ${t.no}</label></div>`;
      } else {
        input = `<input name="${f}" type="number" inputmode="decimal" step="${d.step}" min="${d.min}" ${d.max ? `max="${d.max}"` : ''} placeholder="${d.ph}" value="${v ?? ''}" />`;
      }
      return `<label class="ask-field"><span>${label}${d.hint ? ` <em>${d.hint[lang]}</em>` : ''}</span>${input}</label>`;
    })
    .join('');
  root.innerHTML = `<div class="ask-head"><span class="ask-title">${t.formTitle}</span></div>
    ${note ? `<p class="ask-meta">${esc(note)}</p>` : ''}
    <div class="ask-fields">${rows}</div>
    <p class="ask-err" hidden></p>
    <div class="ask-btns"><button type="submit" class="ask-btn ask-btn--primary">${t.send}</button></div>`;
  host.appendChild(root);

  root.addEventListener('submit', (e) => {
    e.preventDefault();
    const fd = new FormData(root);
    const parts = [];
    const missing = [];
    for (const f of fields) {
      const d = FIELD_DEF[f];
      if (!d) continue;
      const raw = fd.get(f);
      if (raw == null || String(raw).trim() === '') {
        missing.push(d[lang]);
        continue;
      }
      if (d.type === 'select') {
        const opt = d.options.find((o) => o[0] === raw);
        parts.push(`${d[lang]}: ${lang === 'zh' ? opt[2] : opt[1]} (${raw})`);
      } else if (d.type === 'bool') {
        parts.push(`${d[lang]} ${raw === 'yes' ? t.yesWord : t.noWord}`);
      } else {
        const n = parseFloat(raw);
        if (!(n > 0)) {
          missing.push(d[lang]);
          continue;
        }
        parts.push(d.pct ? `${d[lang].replace(/\s*\(%\)|（%）/, '')}: ${n}%` : f === 'cogs_cny' ? `${d[lang]}: ¥${n}` : `${d[lang]}: ${n}`);
      }
    }
    const err = root.querySelector('.ask-err');
    if (missing.length) {
      err.hidden = false;
      err.textContent = (lang === 'zh' ? '请填写：' : 'Please fill in: ') + missing.join(', ');
      return;
    }
    lockWidget(root, root.querySelector('[type=submit]'));
    root.querySelector('[type=submit]').textContent = t.done;
    onSend(parts.join(lang === 'zh' ? '；' : '; ') + (lang === 'zh' ? '。' : '.'));
  });
  return root;
}
