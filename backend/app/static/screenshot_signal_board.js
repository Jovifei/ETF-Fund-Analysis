'use strict';

(() => {
  const board = { payload: null, filter: null, timer: null };
  const byId = (id) => document.getElementById(id);
  const escapeHtml = (value) => String(value ?? '—').replace(/[&<>'"]/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  })[char]);
  const numberValue = (value) => {
    const result = Number(value);
    return Number.isFinite(result) ? result : null;
  };
  const percent = (value, digits = 2) => {
    const result = numberValue(value);
    if (result === null) return '—';
    return `${result >= 0 ? '+' : ''}${result.toFixed(digits)}%`;
  };
  const percentClass = (value) => {
    const result = numberValue(value);
    if (result === null || Math.abs(result) < 1e-12) return 'cn-flat';
    return result > 0 ? 'cn-up' : 'cn-down';
  };
  const priceText = (value) => {
    const result = numberValue(value);
    if (result === null) return '—';
    return result.toFixed(result >= 100 ? 2 : 3);
  };
  const timeText = (value) => {
    if (!value) return '—';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12: false });
  };
  const indicatorValues = (row) => row?.indicator?.values || {};
  const forecastFor = (row, horizon = 1) => (row?.forecasts || []).find((item) => Number(item.horizon) === horizon) || null;

  function privateToken() {
    try {
      if (typeof state !== 'undefined' && state.token) return state.token;
    } catch (_) {}
    return localStorage.getItem('fundDecisionToken')
      || localStorage.getItem('private_access_token')
      || localStorage.getItem('token')
      || '';
  }

  async function request(path) {
    if (typeof api === 'function') {
      try { return await api(path); } catch (_) {}
    }
    const headers = { Accept: 'application/json' };
    const token = privateToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    const response = await fetch(path, { headers });
    if (!response.ok) throw new Error(`${response.status} ${path}`);
    return response.json();
  }

  function groupKey(row) {
    const stateText = String(row?.signal?.state || '');
    const score = numberValue(row?.signal?.score);
    const jValue = numberValue(indicatorValues(row).kdj_j);
    if (/异常|减仓|减少|退出/.test(stateText) || (score !== null && score < 38)) return 'reduce';
    if (/加仓|增加/.test(stateText) || (score !== null && score >= 72 && (jValue === null || jValue < 90))) return 'add';
    if (/入场/.test(stateText) || (score !== null && score >= 66)) return 'entry';
    if (/试探/.test(stateText) || (score !== null && score >= 56)) return 'probe';
    return 'watch';
  }

  function groupTone(key) {
    return {
      add: ['#2ee59f', 'rgba(46,229,159,.12)'],
      entry: ['#50aaff', 'rgba(80,170,255,.12)'],
      probe: ['#ffd142', 'rgba(255,209,66,.11)'],
      watch: ['#ff993d', 'rgba(255,153,61,.11)'],
      reduce: ['#ff646a', 'rgba(255,100,106,.11)']
    }[key] || ['#7c92a7', 'rgba(124,146,167,.1)'];
  }

  function volumeLabel(row) {
    const values = indicatorValues(row);
    const ratio = numberValue(values.volume_ratio);
    const return5 = numberValue(values.return_5d);
    const today = numberValue(row?.quote?.pct_change);
    if (ratio === null) return ['待数据', ''];
    if (ratio >= 1.25 && (today ?? return5 ?? 0) > 0) return [`放量 ${ratio.toFixed(2)}`, 'green'];
    if (ratio >= 1.25 && (today ?? return5 ?? 0) < 0) return [`放量 ${ratio.toFixed(2)}`, 'red'];
    if (ratio <= 0.82) return [`缩量 ${ratio.toFixed(2)}`, 'amber'];
    return [`平量 ${ratio.toFixed(2)}`, 'green'];
  }

  function movingAverageLabel(row) {
    const values = indicatorValues(row);
    const averages = [values.ma5, values.ma10, values.ma20, values.ma30, values.ma60].map(numberValue);
    if (averages.slice(0, 4).every((item) => item !== null)
      && averages[0] > averages[1] && averages[1] > averages[2] && averages[2] > averages[3]) {
      return ['多头排列', 'strong'];
    }
    if (averages.slice(0, 4).every((item) => item !== null)
      && averages[0] < averages[1] && averages[1] < averages[2] && averages[2] < averages[3]) {
      return ['空头排列', 'weak'];
    }
    return ['多空交织', 'mixed'];
  }

  function macdLabel(row) {
    const values = indicatorValues(row);
    const dif = numberValue(values.macd_dif);
    const dea = numberValue(values.macd_dea);
    const hist = numberValue(values.macd_hist);
    if (dif === null || dea === null) return ['待数据', ''];
    if (dif > dea && (hist ?? 0) >= 0) return ['多头延续', 'blue'];
    if (dif > dea) return ['修复延续', 'amber'];
    if (Math.abs(dif - dea) < Math.max(0.001, Math.abs(dea) * 0.08)) return ['将死叉', 'purple'];
    return ['空头延续', 'purple'];
  }

  function kdjLabel(row) {
    const values = indicatorValues(row);
    const jValue = numberValue(values.kdj_j);
    const kValue = numberValue(values.kdj_k);
    const dValue = numberValue(values.kdj_d);
    if (jValue === null) return ['J=—', '', '待数据'];
    if ((kValue !== null && dValue !== null && kValue < dValue) || jValue < 0) return [`J=${jValue.toFixed(1)}`, 'red', '死叉'];
    if (jValue >= 100) return [`J=${jValue.toFixed(1)}`, 'red', '超买'];
    if (jValue >= 85) return [`J=${jValue.toFixed(1)}`, 'amber', '偏高'];
    if (jValue <= 20) return [`J=${jValue.toFixed(1)}`, 'green', '低位'];
    return [`J=${jValue.toFixed(1)}`, 'green', '健康'];
  }

  function tdLabel(row) {
    const values = indicatorValues(row);
    const sell = Math.max(Number(values.td_sell_setup) || 0, 0);
    const buy = Math.max(Number(values.td_buy_setup) || 0, 0);
    if (sell >= 9) return [`TD${Math.min(sell, 13)}`, 'red', '顶部风险'];
    if (buy >= 9) return [`TD${Math.min(buy, 13)}`, 'green', '低位序列'];
    return [String(Math.max(sell, buy) || '—'), '', ''];
  }

  function rsiLabel(row) {
    const value = numberValue(indicatorValues(row).rsi14);
    if (value === null) return ['—', ''];
    if (value >= 72) return [value.toFixed(1), 'cn-up'];
    if (value < 38) return [value.toFixed(1), 'cn-down'];
    if (value < 50) return [value.toFixed(1), 'signal-amber'];
    return [value.toFixed(1), ''];
  }

  function comparisonCell(row) {
    const comparison = row.comparison || {};
    const arrow = comparison.direction === 'up' ? '↑' : comparison.direction === 'down' ? '↓' : '→';
    const css = comparison.direction === 'up' ? 'cn-up' : comparison.direction === 'down' ? 'cn-down' : 'cn-flat';
    const sub = comparison.score_delta == null
      ? '无上一信号'
      : `分值 ${comparison.score_delta >= 0 ? '+' : ''}${Number(comparison.score_delta).toFixed(1)}`;
    return `<span class="metric-main ${css}">${arrow}</span><span class="metric-sub">${sub}</span>`;
  }

  function signalRow(row) {
    const values = indicatorValues(row);
    const forecast1 = forecastFor(row, 1);
    const forecast5 = forecastFor(row, 5);
    const [volume, volumeTone] = volumeLabel(row);
    const [ma, maTone] = movingAverageLabel(row);
    const [macd, macdTone] = macdLabel(row);
    const [kdj, kdjTone, kdjState] = kdjLabel(row);
    const [td, tdTone, tdState] = tdLabel(row);
    const [rsi, rsiClass] = rsiLabel(row);
    const breadth = row.proxy_breadth || {};
    const key = groupKey(row);
    const forecastReturn = numberValue(forecast1?.expected_return);
    const confidence = numberValue(forecast1?.confidence);
    const oneWeek = numberValue(forecast5?.expected_return);
    const today = numberValue(row?.quote?.pct_change);
    return `<tr data-code="${escapeHtml(row.ts_code)}">
      <td class="instrument-cell"><div class="instrument-name">${escapeHtml(row.name)}</div><div class="instrument-sub">${escapeHtml(row.ts_code)} · ${escapeHtml(row.board_profile?.name || row.theme_l1 || '扩展主题')} · ${escapeHtml(row.board_profile?.coverage_status || row.board_profile?.role || '')}</div></td>
      <td><span class="metric-main ${percentClass(today)}">${percent(today)}</span><span class="metric-sub">${priceText(row?.quote?.price)} · ${row?.quote?.timestamp_verified ? '源时刻已验' : '非执行级'}</span></td>
      <td>${comparisonCell(row)}</td>
      <td><span class="signal-pill ${volumeTone}">${escapeHtml(volume)}</span><span class="metric-sub">量能Z ${numberValue(values.volume_zscore)?.toFixed(2) ?? '—'}</span></td>
      <td><div class="ma-lines"><span class="${maTone}">${ma}</span><span class="metric-sub">M5·M10·M20·M30</span><span class="metric-sub">M5=${priceText(values.ma5)} M20=${priceText(values.ma20)}</span></div></td>
      <td><span class="signal-pill ${macdTone}">${macd}</span><span class="metric-sub">DIF=${numberValue(values.macd_dif)?.toFixed(3) ?? '—'} DEA=${numberValue(values.macd_dea)?.toFixed(3) ?? '—'}</span></td>
      <td><span class="signal-pill ${kdjTone}">${escapeHtml(kdj)}</span><span class="metric-sub">${escapeHtml(kdjState)} · K=${numberValue(values.kdj_k)?.toFixed(1) ?? '—'} D=${numberValue(values.kdj_d)?.toFixed(1) ?? '—'}</span></td>
      <td><span class="signal-pill ${tdTone}">${escapeHtml(td)}</span><span class="metric-sub">${escapeHtml(tdState)}</span></td>
      <td><span class="metric-main ${rsiClass}">${escapeHtml(rsi)}</span><span class="metric-sub">${numberValue(values.rsi14) >= 72 ? '超买' : numberValue(values.rsi14) < 38 ? '偏弱' : '趋势中段'}</span></td>
      <td><span class="metric-main"><span class="cn-up">${Number(breadth.up || 0)}涨</span><br><span class="cn-down">${Number(breadth.down || 0)}跌</span></span><span class="metric-sub">${escapeHtml(breadth.label || 'ETF代理池')}</span></td>
      <td><span class="metric-main ${percentClass(oneWeek == null ? null : oneWeek * 100)}">${oneWeek == null ? '—' : percent(oneWeek * 100, 1)}</span><span class="metric-sub">5交易日终点</span></td>
      <td class="forecast-cell"><span class="forecast-return ${percentClass(forecastReturn == null ? null : forecastReturn * 100)}">${forecastReturn == null ? '—' : percent(forecastReturn * 100)}</span><span class="forecast-conf">conf ${confidence == null ? '—' : Math.round(confidence)}</span><span class="forecast-status">${escapeHtml(forecast1?.calibration_status || 'not_calibrated')}</span></td>
      <td><span class="recommendation ${key}">${escapeHtml(row?.signal?.state || ({ add:'可加仓', entry:'可入场', probe:'可试探', watch:'观望', reduce:'减仓' })[key])}</span><span class="metric-sub">分 ${numberValue(row?.signal?.score)?.toFixed(1) ?? '—'}</span></td>
    </tr>`;
  }

  function renderSummary(rows, payload) {
    const counts = { add: 0, entry: 0, probe: 0, watch: 0, reduce: 0 };
    let up = 0;
    let down = 0;
    rows.forEach((row) => {
      counts[groupKey(row)] += 1;
      const change = numberValue(row?.quote?.pct_change);
      if (change > 0) up += 1;
      else if (change < 0) down += 1;
    });
    const cards = [
      [payload.coverage?.total ?? 31, '行业板块', `${payload.coverage?.direct ?? 0}直接 · ${payload.coverage?.proxy ?? 0}代理`, '#41a7ff'],
      [counts.add, '可加仓', '高分且不过热', '#2ee59f'],
      [counts.entry, '可入场', '结构向好', '#50aaff'],
      [counts.probe, '可试探', '小仓验证', '#ffd142'],
      [counts.watch, '观望', '等待确认', '#ff993d'],
      [counts.reduce, '减仓/异常', '风险门控', '#ff646a']
    ];
    byId('screenshotSummaryCards').innerHTML = cards.map(([count, label, note, tone]) => `<article class="screenshot-summary-card" style="--card-tone:${tone}"><strong>${count}</strong><span>${label}</span><small>${note}</small></article>`).join('');
    const ranked = rows.filter((row) => numberValue(row?.signal?.score) !== null);
    const top = [...ranked].sort((a, b) => numberValue(b.signal.score) - numberValue(a.signal.score))[0];
    const risk = [...ranked].sort((a, b) => numberValue(a.signal.score) - numberValue(b.signal.score))[0];
    byId('screenshotIntradaySummary').innerHTML = `<strong>盘中总结：</strong><span>ETF代理池 <b class="cn-up">${up}只上涨</b>、<b class="cn-down">${down}只下跌</b>。当前高分标的：<b>${escapeHtml(top?.name || '—')}</b>（${numberValue(top?.signal?.score)?.toFixed(1) ?? '—'}）；风险靠前：<b>${escapeHtml(risk?.name || '—')}</b>（${numberValue(risk?.signal?.score)?.toFixed(1) ?? '—'}）。板块涨跌为ETF代理池口径，不是行业成份股家数；预测未校准时仅作研究。</span>`;
  }

  function renderAnchors(rows, payload) {
    const byCode = new Map(rows.map((row) => [row.ts_code, row]));
    byId('screenshotAnchorGrid').innerHTML = (payload.market_anchors || []).map((anchor, index) => {
      const row = byCode.get(anchor.proxy_ts_code) || {};
      const values = indicatorValues(row);
      const forecast = forecastFor(row, 1);
      const change = numberValue(row?.quote?.pct_change);
      const [macd] = macdLabel(row);
      const [kdj, , kdjState] = kdjLabel(row);
      const [ma] = movingAverageLabel(row);
      const glow = ['rgba(65,167,255,.14)', 'rgba(255,92,98,.13)', 'rgba(192,92,255,.13)', 'rgba(255,178,47,.13)'][index % 4];
      return `<article class="anchor-card" style="--anchor-glow:${glow}"><h3>${escapeHtml(anchor.name)} · ${escapeHtml(anchor.proxy_name)}</h3><div class="anchor-code">${escapeHtml(anchor.proxy_ts_code)} · ${escapeHtml(anchor.kind)}</div><div class="anchor-price-row"><span class="anchor-price">${priceText(row?.quote?.price)}</span><span class="anchor-pct ${percentClass(change)}">${percent(change)}</span></div><div class="anchor-metrics"><span>量能 <b>${numberValue(values.volume_ratio)?.toFixed(2) ?? '—'}</b></span><span>均线 <b>${ma}</b></span><span>MACD <b>${macd}</b></span><span>KDJ <b>${kdjState || kdj}</b></span><span>RSI <b>${numberValue(values.rsi14)?.toFixed(1) ?? '—'}</b></span><span>明日 <b class="${percentClass((numberValue(forecast?.expected_return) || 0) * 100)}">${forecast ? percent(numberValue(forecast.expected_return) * 100) : '—'}</b></span></div><div class="proxy-warning">${escapeHtml(anchor.note)}</div></article>`;
    }).join('');
  }

  function renderIndustries(payload) {
    const industries = payload.industries || [];
    byId('industryCoverageMeta').textContent = `${payload.coverage?.direct ?? 0}直接ETF · ${payload.coverage?.proxy ?? 0}主题代理 · ${payload.coverage?.unmapped ?? 0}待映射`;
    byId('screenshotIndustryChips').innerHTML = `<button class="industry-chip active" data-industry="">全部</button>` + industries.map((industry) => {
      const css = industry.coverage_status === 'direct_etf' ? 'direct' : industry.coverage_status === 'proxy' ? 'proxy' : 'unmapped';
      return `<button class="industry-chip ${css}" data-industry="${escapeHtml(industry.name)}" ${css === 'unmapped' ? 'disabled' : ''} title="${escapeHtml(industry.coverage_note)}">${escapeHtml(industry.name)}${industry.proxy_name ? ` · ${escapeHtml(industry.proxy_name)}` : ''}</button>`;
    }).join('');
    byId('screenshotIndustryChips').querySelectorAll('button[data-industry]').forEach((button) => button.addEventListener('click', () => {
      board.filter = button.dataset.industry || null;
      byId('screenshotIndustryChips').querySelectorAll('button').forEach((item) => item.classList.toggle('active', item === button));
      renderGroups();
    }));
  }

  function renderGroups() {
    if (!board.payload) return;
    const allRows = board.payload.rows || [];
    const rows = board.filter
      ? allRows.filter((row) => (row.board_profile?.name || row.theme_l1) === board.filter)
      : allRows;
    byId('screenshotActiveFilter').textContent = board.filter ? `当前行业：${board.filter}` : '当前：全部行业与扩展主题';
    const configs = board.payload.signal_groups || [];
    byId('screenshotSignalGroups').innerHTML = configs.map((group) => {
      const list = rows.filter((row) => groupKey(row) === group.key);
      const [tone, soft] = groupTone(group.key);
      const table = list.length
        ? `<div class="screenshot-table-wrap"><table class="screenshot-table"><thead><tr><th class="instrument-cell">标的</th><th>今日涨幅</th><th>较昨日</th><th>量能</th><th>均线多空</th><th>MACD</th><th>KDJ</th><th>九转</th><th>RSI</th><th>板块涨跌</th><th>近1周</th><th>明日预测</th><th>操作建议</th></tr></thead><tbody>${list.map(signalRow).join('')}</tbody></table></div>`
        : `<div class="signal-group-empty">今日无「${escapeHtml(group.label)}」标的</div>`;
      return `<section class="signal-group" style="--group-tone:${tone};--group-soft:${soft}"><header class="signal-group-head"><div class="signal-group-title"><span class="signal-group-badge">${escapeHtml(group.label)}</span><span>${escapeHtml(group.subtitle)}</span></div><span class="signal-group-count">${list.length}个标的</span></header>${table}</section>`;
    }).join('');
    renderInsights(rows);
  }

  function renderInsights(rows) {
    const changes = [...rows]
      .filter((row) => row.comparison?.score_delta != null)
      .sort((a, b) => Math.abs(numberValue(b.comparison.score_delta)) - Math.abs(numberValue(a.comparison.score_delta)))
      .slice(0, 5);
    const forecasts = [...rows]
      .filter((row) => forecastFor(row, 1))
      .sort((a, b) => (numberValue(forecastFor(b, 1)?.expected_return) ?? -9) - (numberValue(forecastFor(a, 1)?.expected_return) ?? -9))
      .slice(0, 5);
    byId('screenshotCoreChanges').innerHTML = `<ul class="insight-list">${changes.length ? changes.map((row) => `<li><strong>${escapeHtml(row.name)}</strong>：信号分 ${row.comparison.score_delta >= 0 ? '+' : ''}${Number(row.comparison.score_delta).toFixed(1)}，${escapeHtml(row.comparison.previous_state || '上一状态未知')} → ${escapeHtml(row.signal?.state || '观察')}；${escapeHtml((row.signal?.reasons || []).slice(0, 2).join('、') || '等待更多证据')}</li>`).join('') : '<li>暂无可比较的上一信号快照。</li>'}<li>板块涨跌采用ETF代理池口径；行业成份股广度需要独立数据源。</li></ul>`;
    byId('screenshotNextDay').innerHTML = `<ul class="insight-list">${forecasts.length ? forecasts.map((row) => {
      const forecast = forecastFor(row, 1);
      return `<li><strong>${escapeHtml(row.name)}</strong>：明日 ${percent(numberValue(forecast.expected_return) * 100)}，P(up) ${numberValue(forecast.p_up) == null ? '—' : percent(numberValue(forecast.p_up) * 100, 0)}，conf ${Math.round(numberValue(forecast.confidence) || 0)}；终点中位 ${priceText(forecast.terminal_price_q50)}，路径支撑 ${priceText(forecast.path_low_price_q50)}，压力 ${priceText(forecast.path_high_price_q50)}；${escapeHtml(forecast.calibration_status || 'not_calibrated')}</li>`;
    }).join('') : '<li>暂无明日预测样本。</li>'}<li>置信度来自样本与模型稳定性，不是收益保证。</li></ul>`;
  }

  async function loadBoard() {
    if (!byId('screenshotSignalBoard')) return;
    try {
      const payload = await request('/api/signal-board');
      board.payload = payload;
      const rows = payload.rows || [];
      byId('screenshotBoardMeta').textContent = `${payload.version || 'signal-board'} · ${rows.length}标的 · ${timeText(payload.generated_at)} · ${payload.breadth_scope || ''}`;
      renderSummary(rows, payload);
      renderAnchors(rows, payload);
      renderIndustries(payload);
      renderGroups();
    } catch (error) {
      byId('screenshotBoardMeta').textContent = `信号板加载失败：${error.message}`;
      byId('screenshotIntradaySummary').innerHTML = '<strong>数据不可用：</strong><span>请检查私有访问令牌、数据库初始化和 /api/signal-board。</span>';
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    loadBoard();
    const refreshButton = byId('refreshButton');
    if (refreshButton) refreshButton.addEventListener('click', () => setTimeout(loadBoard, 180));
    board.timer = setInterval(loadBoard, 180000);
  });
})();
