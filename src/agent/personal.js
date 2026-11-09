// Personalisation for the agent page: the seller's profile (from onboarding), the welcome
// screen, sign-in-to-save, and saved products. Guests keep their profile in the browser;
// an account adds sync across devices and saved products.

import { esc } from '../lib/markdown.js';
import { postJSON } from '../lib/agentStream.js';
import { createOnboarding, nicheInfo, NICHE_LIST, catLabel, nicheLabel, platformLabel, COST_BANDS } from './onboarding.js';

const KEY = 'landed-profile';
const OWN_KEYS = ['fee_rate', 'freight_cny_per_kg', 'return_rate', 'fx'];
import { marketName } from '../lib/markets.js';

const P = {
  zh: {
    login: '登录',
    authTitle: '登录 / 注册',
    greetNew: '你好，我是到岸。',
    greetBack: '欢迎回来。',
    introBack: '你的设置已经就绪：只要告诉我产品的成本和重量，我直接按你的数字报价。',
    introGuest: '告诉我卖什么、卖到哪（欧盟国家或美国）、单件成本、重量和目标毛利。信息齐了我直接给售价，只有会影响价格的问题我才会问。',
    personalise: '用 30 秒个性化我的工作台 →',
    startersLabel: '试试这些：',
    startersLabelMine: '按你的品类，只需成本和重量：',
    noMarketHint: '，卖德国',
    marginHint: '，目标毛利 25%',
    pack2: (name) => `${name}（2 件装）`,
    withGift: (name) => `${name}，搭配一个赠品`,
    edit: '修改',
    savedTitle: '我保存的产品',
    open: '打开',
    remove: '删除',
    saveProduct: '保存这个产品',
    saved: '已保存 ✓',
    saveTitle: '保存产品',
    saveName: '给它起个名字',
    saveConfirm: '保存',
    needLogin: '登录后即可保存产品，并在任何设备上继续使用你的设置。',
    tabLogin: '登录',
    tabRegister: '注册',
    email: '邮箱',
    password: '密码（至少 8 位）',
    consent: '我已阅读并同意下面的隐私说明',
    privacy: '我们只保存：邮箱、加密后的密码、你填写的设置和保存的产品，用于登录和跨设备同步，不用于广告、不出售。你的对话内容会发送给智谱 GLM 模型来生成回复。你可以随时在账户里删除账号和全部数据。',
    submitLogin: '登录',
    submitRegister: '注册并保存',
    errors: { 401: '邮箱或密码不对', 409: '这个邮箱已经注册，请直接登录', 422: '请检查邮箱格式、密码长度，并勾选同意隐私说明', 429: '尝试次数太多，请几分钟后再试', x: '暂时无法完成，请稍后再试' },
    account: '账户',
    settings: '个性化设置',
    signedAs: '已登录：',
    logout: '退出登录',
    deleteAcc: '删除账号和全部数据',
    deleteConfirm: '确定删除？你的设置和保存的产品会被永久删除，无法恢复。',
    settingsSaved: '设置已保存',
    margin: '目标毛利',
    fee: '平台佣金',
    freight: '运费',
    returns: '退货率'
  },
  en: {
    login: 'Sign in',
    authTitle: 'Sign in / Register',
    greetNew: 'Hi, I’m Landed.',
    greetBack: 'Welcome back.',
    introBack: 'Your setup is ready: give me a product’s cost and weight and I price it with your numbers.',
    introGuest: 'Tell me what you sell, where (an EU country or the US), the unit cost, weight and target margin. With those I give you a price right away, and I only ask questions that change it.',
    personalise: 'Personalise my workspace in 30 seconds →',
    startersLabel: 'Try one:',
    startersLabelMine: 'For your category, it only needs cost and weight:',
    noMarketHint: ', Germany',
    marginHint: ', 25% target margin',
    pack2: (name) => `${name} 2-pack`,
    withGift: (name) => `${name} with a free gift`,
    edit: 'Edit',
    savedTitle: 'My saved products',
    open: 'Open',
    remove: 'Delete',
    saveProduct: 'Save this product',
    saved: 'Saved ✓',
    saveTitle: 'Save product',
    saveName: 'Give it a name',
    saveConfirm: 'Save',
    needLogin: 'Sign in to save products and keep your setup on every device.',
    tabLogin: 'Sign in',
    tabRegister: 'Register',
    email: 'Email',
    password: 'Password (8+ characters)',
    consent: 'I have read and agree to the privacy note below',
    privacy: 'We store only your email, an encrypted password, the setup you enter and the products you save, to sign you in and sync across devices. No ads, no selling. Your chat messages are sent to the Zhipu GLM model to write replies. You can delete your account and all data at any time.',
    submitLogin: 'Sign in',
    submitRegister: 'Register and save',
    errors: { 401: 'Wrong email or password', 409: 'This email is already registered, please sign in', 422: 'Check the email, a password of 8+ characters, and tick the privacy consent', 429: 'Too many attempts, please try again in a few minutes', x: 'Something went wrong, please try again' },
    account: 'Account',
    settings: 'Personal settings',
    signedAs: 'Signed in as ',
    logout: 'Sign out',
    deleteAcc: 'Delete account and all data',
    deleteConfirm: 'Delete for good? Your setup and saved products will be permanently removed.',
    settingsSaved: 'Settings saved',
    margin: 'Target margin',
    fee: 'Platform fee',
    freight: 'Freight',
    returns: 'Return rate'
  }
};

const $ = (id) => document.getElementById(id);

function readLocal() {
  try {
    return JSON.parse(localStorage.getItem(KEY) || '{}') || {};
  } catch {
    return {};
  }
}
function writeLocal(v) {
  try {
    localStorage.setItem(KEY, JSON.stringify(v));
  } catch {
    /* storage blocked: the setup lasts for this visit only */
  }
}

export function createPersonal(h) {
  const L = () => P[h.getLang()];
  let local = readLocal(); // { profile, skipped }
  let user = null;
  let products = [];
  let afterLogin = null;
  let authMode = 'login';

  const profile = () => local.profile || {};
  const hasProfile = () => Object.keys(profile()).length > 0;

  const onboarding = createOnboarding({
    getLang: h.getLang,
    toggleLang: () => h.toggleLang(),
    getProfile: profile,
    onDone: async (p) => {
      await persistProfile(p);
      renderWelcome();
      h.toast(L().settingsSaved);
    },
    onSkip: () => {
      local = { ...local, skipped: true };
      writeLocal(local);
      renderWelcome();
    }
  });

  // ---------------------------------------------------------------- data
  async function persistProfile(p) {
    local = { profile: p, skipped: false };
    writeLocal(local);
    if (user) {
      try {
        await fetch('/api/profile', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(p) });
      } catch {
        /* kept locally; syncs on the next save */
      }
    }
    h.onChange();
  }

  async function loadProducts() {
    if (!user) {
      products = [];
      return;
    }
    try {
      products = (await fetch('/api/products').then((r) => r.json())).products || [];
    } catch {
      products = [];
    }
  }

  async function init() {
    try {
      const me = await fetch('/api/me').then((r) => r.json());
      user = me.user;
    } catch {
      user = null;
    }
    if (user) {
      const server = user.profile || {};
      if (Object.keys(server).length) {
        local = { profile: server, skipped: false };
        writeLocal(local);
      } else if (hasProfile()) {
        await persistProfile(profile());
      }
      await loadProducts();
    }
    paintAccount();
    relabel();
    h.onChange();
    // A first visit starts with the onboarding, before the agent page proper.
    if (!hasProfile() && !local.skipped) onboarding.open({ edit: false });
  }

  // ---------------------------------------------------------------- derived
  function overrides() {
    const p = profile();
    return Object.fromEntries(OWN_KEYS.filter((k) => p[k] != null).map((k) => [k, p[k]]));
  }
  const chatProfile = () => (hasProfile() ? profile() : null);

  // ---------------------------------------------------------------- welcome
  function summaryChips() {
    const p = profile();
    const lang = h.getLang();
    const l = L();
    const out = [];
    if (p.niche || p.category) out.push(p.niche ? nicheLabel(p.niche, lang) : catLabel(p.category, lang));
    if (p.market) out.push(marketName(p.market, lang));
    if (p.platform) out.push(platformLabel(p.platform, lang));
    if (p.target_margin) out.push(`${l.margin} ${+(p.target_margin * 100).toFixed(1)}%`);
    if (p.fee_rate != null) out.push(`${l.fee} ${+(p.fee_rate * 100).toFixed(1)}%`);
    if (p.freight_cny_per_kg != null) out.push(`${l.freight} ¥${p.freight_cny_per_kg}/kg`);
    if (p.return_rate != null) out.push(`${l.returns} ${+(p.return_rate * 100).toFixed(1)}%`);
    return out;
  }

  function starterTexts() {
    const p = profile();
    const lang = h.getLang();
    const l = L();
    const fallback = NICHE_LIST.filter((n) => ['basics', 'kitchen_appliance', 'phone_acc'].includes(n[0]));
    const info = p.niche ? nicheInfo(p.niche) : null;
    const make = (n, mult = 1, wrap = (x) => x) => {
      const name = wrap(lang === 'zh' ? n[3] : n[4]);
      const cost = +((p.cost_band ? COST_BANDS[p.cost_band] : n[5]) * mult).toFixed(1);
      const kg = +(n[6] * mult).toFixed(2);
      const market = p.market ? '' : l.noMarketHint;
      const margin = p.target_margin ? '' : l.marginHint;
      return lang === 'zh' ? `${name}，成本 ${cost} 元，重 ${kg} kg${market}${margin}` : `${name}, cost ¥${cost}, ${kg} kg${market}${margin}`;
    };
    if (!info) return fallback.map((n) => make(n));
    const list = [make(info), make(info, 2, l.pack2)];
    if (p.parcel === 'mixed') list.push(make(info, 1.3, l.withGift));
    return list;
  }

  function renderWelcome() {
    const log = $('chat-log');
    if (!log || log.dataset.started === '1') return; // a conversation is under way
    let host = $('welcome');
    if (!host) {
      host = document.createElement('div');
      host.id = 'welcome';
      host.className = 'welcome';
      log.prepend(host);
    }
    const l = L();
    const mine = hasProfile();
    host.innerHTML = `<div class="msg msg--agent msg--intro"><p class="msg__title">${esc(mine || user ? l.greetBack : l.greetNew)}</p><p>${esc(mine ? l.introBack : l.introGuest)}</p></div>`;
    if (mine) {
      const sum = document.createElement('div');
      sum.className = 'summary';
      sum.innerHTML = `${summaryChips().map((c) => `<span class="chip">${esc(c)}</span>`).join('')}<button type="button" class="btn btn--quiet" data-act="edit">${esc(l.edit)}</button>`;
      sum.querySelector('[data-act=edit]').addEventListener('click', openSettings);
      host.appendChild(sum);
    } else {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn btn--primary btn--personalise';
      b.textContent = l.personalise;
      b.addEventListener('click', () => onboarding.open({ edit: false }));
      host.appendChild(b);
    }
    const st = document.createElement('div');
    st.className = 'starters';
    st.innerHTML = `<p class="starters__label">${esc(mine && profile().niche ? l.startersLabelMine : l.startersLabel)}</p>` + starterTexts().map((t, i) => `<button type="button" class="starter" data-s="${i}">${esc(t)}</button>`).join('');
    st.querySelectorAll('[data-s]').forEach((b) => b.addEventListener('click', () => h.send(b.textContent)));
    host.appendChild(st);
    if (products.length) {
      const sv = document.createElement('div');
      sv.className = 'saved';
      sv.innerHTML = `<p class="starters__label">${esc(l.savedTitle)}</p>` +
        products.map((p) => `<div class="saved__row"><span class="saved__name">${esc(p.name)}</span><span class="saved__price">${esc(p.data.priceText || '')}</span>
          <button type="button" class="btn btn--quiet" data-open="${p.id}">${esc(l.open)}</button><button type="button" class="btn btn--quiet" data-del="${p.id}" aria-label="${esc(l.remove)}">×</button></div>`).join('');
      sv.querySelectorAll('[data-open]').forEach((b) => b.addEventListener('click', () => h.openProduct(products.find((x) => x.id === +b.dataset.open).data)));
      sv.querySelectorAll('[data-del]').forEach((b) => b.addEventListener('click', async () => {
        await fetch(`/api/products/${b.dataset.del}`, { method: 'DELETE' });
        await loadProducts();
        renderWelcome();
      }));
      host.appendChild(sv);
    }
  }

  const openSettings = () => onboarding.open({ edit: true });

  // ---------------------------------------------------------------- auth + account
  function paintAccount() {
    const b = $('lw-account');
    if (!b) return;
    b.textContent = user ? user.email.split('@')[0].slice(0, 12) : L().login;
    b.title = user ? user.email : '';
  }

  function openAuth(reason, cb) {
    afterLogin = cb || null;
    if (user) return openAccount();
    setMode('login');
    $('auth-reason').textContent = reason ? L().needLogin : '';
    $('auth-reason').hidden = !reason;
    $('auth-err').hidden = true;
    $('dlg-auth').showModal();
  }
  function setMode(m) {
    authMode = m;
    $('dlg-auth').querySelectorAll('[data-mode]').forEach((b) => b.classList.toggle('is-on', b.dataset.mode === m));
    $('auth-consent-row').hidden = m !== 'register';
    $('auth-privacy').hidden = m !== 'register';
    $('auth-submit').textContent = m === 'register' ? L().submitRegister : L().submitLogin;
    $('auth-pw').autocomplete = m === 'register' ? 'new-password' : 'current-password';
  }
  async function submitAuth(e) {
    e.preventDefault();
    const err = $('auth-err');
    err.hidden = true;
    try {
      const body = { email: $('auth-email').value, password: $('auth-pw').value, consent: $('auth-consent').checked };
      const r = await fetch(`/api/auth/${authMode}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
      if (!r.ok) {
        err.textContent = L().errors[r.status] || L().errors.x;
        err.hidden = false;
        return;
      }
      user = await r.json();
      $('auth-pw').value = '';
      $('dlg-auth').close();
      const server = user.profile || {};
      if (Object.keys(server).length) {
        local = { profile: server, skipped: false };
        writeLocal(local);
      } else if (hasProfile()) await persistProfile(profile());
      await loadProducts();
      paintAccount();
      renderWelcome();
      h.onChange();
      const cb = afterLogin;
      afterLogin = null;
      if (cb) cb();
    } catch {
      err.textContent = L().errors.x;
      err.hidden = false;
    }
  }
  function openAccount() {
    $('acc-email').textContent = L().signedAs + user.email;
    $('dlg-account').showModal();
  }
  async function logout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    user = null;
    products = [];
    $('dlg-account').close();
    paintAccount();
    renderWelcome();
  }
  async function deleteAccount() {
    if (!window.confirm(L().deleteConfirm)) return;
    await fetch('/api/me', { method: 'DELETE' });
    user = null;
    products = [];
    local = {};
    writeLocal(local);
    $('dlg-account').close();
    paintAccount();
    renderWelcome();
    h.onChange();
  }

  // ---------------------------------------------------------------- saved products
  function save() {
    const snap = h.snapshot();
    if (!snap) return;
    if (!user) return openAuth(true, () => save());
    $('save-name').value = snap.name;
    $('dlg-save').showModal();
    $('save-name').select();
  }
  async function confirmSave(e) {
    e.preventDefault();
    const snap = h.snapshot();
    if (!snap) return;
    try {
      await postJSON('/api/products', { name: $('save-name').value.trim() || snap.name, data: snap.data });
      $('dlg-save').close();
      await loadProducts();
      const b = $('btn-save');
      if (b) {
        b.textContent = L().saved;
        setTimeout(() => (b.textContent = L().saveProduct), 2500);
      }
      renderWelcome();
    } catch (err) {
      h.toast(err.message);
    }
  }

  // ---------------------------------------------------------------- copy
  function relabel() {
    document.querySelectorAll('[data-p]').forEach((el) => {
      const v = L()[el.dataset.p];
      if (typeof v === 'string') el.textContent = v;
    });
    $('auth-email')?.setAttribute('placeholder', L().email);
    $('auth-pw')?.setAttribute('placeholder', L().password);
    paintAccount();
    if ($('dlg-auth')) setMode(authMode);
    $('lw-settings')?.setAttribute('aria-label', L().settings);
    renderWelcome();
    onboarding.relabel();
  }

  function bind() {
    $('lw-account').addEventListener('click', () => (user ? openAccount() : openAuth(false)));
    $('lw-settings').addEventListener('click', openSettings);
    $('auth-form').addEventListener('submit', submitAuth);
    $('dlg-auth').querySelectorAll('[data-mode]').forEach((b) => b.addEventListener('click', () => setMode(b.dataset.mode)));
    $('btn-save')?.addEventListener('click', save);
    $('save-form').addEventListener('submit', confirmSave);
    $('acc-logout').addEventListener('click', logout);
    $('acc-delete').addEventListener('click', deleteAccount);
    document.querySelectorAll('dialog [data-close]').forEach((b) => b.addEventListener('click', () => b.closest('dialog').close()));
    document.querySelectorAll('dialog').forEach((d) =>
      d.addEventListener('click', (e) => {
        if (e.target === d) d.close(); // click on the backdrop
      })
    );
  }

  return {
    init, bind, relabel, renderWelcome, overrides, chatProfile, hasProfile, profile,
    summary: summaryChips, openAuth, save,
    markStarted: () => {
      const lg = $('chat-log');
      if (lg) lg.dataset.started = '1';
      ['.starters', '.saved', '.btn--personalise'].forEach((s) => $('welcome')?.querySelector(s)?.remove());
    },
    get user() { return user; }
  };
}
