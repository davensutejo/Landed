// Shared client for the streaming /api/chat endpoint (SSE over fetch POST).

export const API_BASE = window.LANDED_API_BASE || '';

export const TOOL_LABEL = {
  classify_hs: 'HS 归类 · classify_hs',
  landed_cost: '到岸成本 · landed_cost',
  compliance_flags: '合规 · compliance_flags',
  ask_seller: '追问 · ask_seller'
};

export function summarize(name, result) {
  if (!result) return '';
  if (result.status === 'abstain') return 'ABSTAIN · not in verified tables';
  if (result.error) return `error · ${result.error}`;
  if (name === 'classify_hs') {
    const top = (result.candidates || []).map((c) => c.hs).join(' / ');
    return `${result.status} · ${top}${result.next_question ? ' · ask: ' + result.next_question.attribute : ''}`;
  }
  if (name === 'landed_cost') {
    const wf = result.waterfall;
    const mc = result.monte_carlo;
    return `${wf.currency} ${wf.price} · floor95 ${mc.floor_price_95} · P5 ${(mc.p5_margin * 100).toFixed(1)}%`;
  }
  if (name === 'compliance_flags') return `${(result.flags || []).length} flags`;
  if (name === 'ask_seller') return `form · ${(result.fields || []).join(', ')}`;
  return '';
}

export async function streamChat(messages, onEvent, { signal, profile } = {}) {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(profile ? { messages, profile } : { messages }),
    signal
  });
  if (!res.ok || !res.body) {
    throw new Error(res.status === 429 ? '请求过于频繁，请稍后再试 · rate limited' : `HTTP ${res.status}`);
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, idx).replace(/^data:\s?/, '');
      buf = buf.slice(idx + 2);
      if (chunk.trim()) onEvent(JSON.parse(chunk));
    }
  }
}

export async function postJSON(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body)
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail || {};
    throw new Error(d.error || d || `HTTP ${res.status}`);
  }
  return data;
}
