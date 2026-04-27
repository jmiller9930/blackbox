/**
 * Pattern Machine learning — banner strip bootstrap (loaded as external script).
 * Same-origin file satisfies typical CSP (script-src 'self') when inline script is blocked.
 */
(function pgBannerApiBootstrap() {
  function esc(s) {
    const d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
  }

  const ht = document.getElementById('healthText');
  const hd = document.getElementById('healthDot');
  const bf = document.getElementById('bannerFinancialV');
  fetch('/api/data-health')
    .then(function (r) {
      return r.json();
    })
    .then(function (j) {
      if (!ht) return;
      try {
        if (hd) {
          hd.className = 'status-dot ' + (j && j.overall_ok ? 'ok' : 'bad');
          hd.title = j && j.overall_ok ? 'Data OK' : 'Data issue — see text';
        }
        if (bf) bf.textContent = j && j.overall_ok ? 'OK' : 'Issue';
        if (j && j.summary_line) ht.textContent = j.summary_line;
        else if (j && j.error) ht.textContent = j.error;
        else ht.textContent = j ? 'Unknown status' : 'No data';
      } catch (_e) { /* ignore */ }
    })
    .catch(function (e) {
      if (ht) ht.textContent = 'Health check failed: ' + (e && e.message ? e.message : String(e));
      if (hd) {
        hd.className = 'status-dot bad';
        hd.title = 'Health request failed';
      }
      if (bf) bf.textContent = '—';
    });

  const st = document.getElementById('reasoningModelHeadV');
  const core = document.getElementById('reasoningModelCoreS');
  const cost = document.getElementById('reasoningModelCostS');
  const tile = document.getElementById('reasoningModelBannerTile');
  const gw = document.getElementById('rmExtGatewayChk');
  const addFunds = document.getElementById('rmAddFundsLink');

  function rmTileClass(c) {
    if (!tile) return;
    tile.classList.remove('rm-sig-green', 'rm-sig-amber', 'rm-sig-red', 'rm-sig-blue');
    const x = String(c || 'amber');
    if (x === 'green') tile.classList.add('rm-sig-green');
    else if (x === 'red') tile.classList.add('rm-sig-red');
    else if (x === 'blue') tile.classList.add('rm-sig-blue');
    else tile.classList.add('rm-sig-amber');
  }

  var rmStatusUrl = '/api/reasoning-model/status';
  try {
    var infl = String(localStorage.getItem('patternGame.parallelInflightJobId') || '').trim();
    if (infl && /^[a-f0-9]{32}$/i.test(infl)) {
      rmStatusUrl += '?job_id=' + encodeURIComponent(infl);
    }
  } catch (_e) { /* */ }
  fetch(rmStatusUrl)
    .then(function (r) {
      return r.json();
    })
    .then(function (j) {
      if (!st) return;
      if (!j || !j.ok) {
        st.textContent = '—';
        if (core) core.textContent = 'Status unavailable';
        if (cost) cost.textContent = '';
        rmTileClass('red');
        if (tile) tile.title = 'Reasoning Model status unavailable';
        return;
      }
      var f = j.fields_v1 || {};
      st.textContent = f.headline_badge_v1 != null ? String(f.headline_badge_v1) : (j.status_headline_v1 || '—');
      if (j.external_api_proof_line_v1) st.setAttribute('data-external-line', String(j.external_api_proof_line_v1));
      else st.removeAttribute('data-external-line');
      if (core) {
        if (f.ui_core_lines_v1 && f.ui_core_lines_v1.length) {
          core.style.whiteSpace = 'pre-line';
          core.textContent = f.ui_core_lines_v1.map(function (l) { return String(l); }).join('\n');
        } else {
          core.textContent = f.external_api_proof_line_v1 != null ? String(f.external_api_proof_line_v1) : '—';
        }
      }
      if (cost) {
        var cost0 = f.run_cost_display_v1 != null ? String(f.run_cost_display_v1) : '$0.00';
        var cap0 = f.budget_cap_display_v1 != null ? String(f.budget_cap_display_v1) : '—';
        var lastR0 = f.last_external_call_result_v1 != null ? String(f.last_external_call_result_v1) : '—';
        var runB0 = f.external_api_balance_status_v1 != null ? String(f.external_api_balance_status_v1) : '—';
        cost.textContent =
          'Run cost: ' + cost0 + ' · Budget cap: ' + cap0 + ' · Run headroom: ' + runB0 + ' · Last call: ' + lastR0;
      }
      if (addFunds && j.add_funds_billing_url_v1) {
        addFunds.href = String(j.add_funds_billing_url_v1);
      }
      rmTileClass(j.tile_color_v1 || 'amber');
      if (tile) {
        var br = f.block_reasons_v1;
        var tok = f.tokens_current_run_v1 || {};
        var msg0 = f.operator_block_message_v1 && String(f.operator_block_message_v1).trim() ? f.operator_block_message_v1 : '';
        tile.title = [
          j.external_api_proof_line_v1 != null ? String(j.external_api_proof_line_v1) : '',
          msg0 || (j.escalation_summary_v1 != null ? String(j.escalation_summary_v1) : ''),
          (j.job_id_scoped != null) ? 'job_id (scope): ' + j.job_id_scoped : 'No ?job_id= in URL — add to scope a run for trace',
          f.funding_note_v1 != null ? String(f.funding_note_v1) : '',
          j.primary_escalation_code_v1 != null ? 'Debug code: ' + j.primary_escalation_code_v1 : '',
          'Tokens: ' + (tok && tok.input != null ? tok.input : '—') + ' in, ' + (tok && tok.output != null ? tok.output : '—') + ' out',
          br && br.length ? 'Blockers: ' + br.join(', ') : '',
        ]
          .filter(function (x) { return x; })
          .join('\n');
      }
      if (gw && j.operator_external_api_gateway_allows_v1 != null) {
        gw.checked = !!j.operator_external_api_gateway_allows_v1;
      }
    })
    .catch(function (e) {
      if (st) st.textContent = '—';
      if (core) core.textContent = e && e.message ? e.message : String(e);
      if (cost) cost.textContent = '';
      rmTileClass('red');
      if (tile) tile.title = e && e.message ? e.message : String(e);
    });

  var ss = document.getElementById('searchSpaceStrip');
  if (ss) {
    fetch('/api/search-space-estimate?workers=1')
      .then(function (r) {
        return r.json();
      })
      .then(function (j) {
        var m = j.catalog && j.catalog.signals_count;
        var subU = j.combinatorics && j.combinatorics.non_empty_signal_subsets_upper_bound;
        var bars = j.dataset && j.dataset.market_bars_5m_count;
        var line = '<strong>Search space</strong> — ';
        if (m != null && subU != null) {
          line +=
            m +
            ' catalog signals → up to <strong>' +
            subU +
            '</strong> non-empty signal subsets (2^' +
            m +
            '−1; validation may disallow some). ';
        }
        if (bars != null) {
          line += '<strong>' + bars.toLocaleString() + '</strong> rows in <code>market_bars_5m</code>. ';
        } else if (j.dataset && j.dataset.error) {
          line += 'Bars: unavailable (' + String(j.dataset.error).slice(0, 120) + '). ';
        }
        line += 'Pick a pattern (or Custom JSON) to see batch rounds; workers use slider (1). ';
        ss.innerHTML = line;
      })
      .catch(function (e) {
        ss.innerHTML =
          '<strong>Search space</strong> — could not load estimate. ' + (e && e.message ? e.message : String(e));
      });
  }

  var list = document.getElementById('moduleBoardList');
  var md = document.getElementById('moduleBannerDot');
  var bmv = document.getElementById('bannerModulesV');
  var bms = document.getElementById('bannerModulesS');
  var fSt = document.getElementById('focusTileModulesSt');
  var fLn = document.getElementById('focusTileModulesLine');

  function setModuleBannerEarly(okCount, total, sub) {
    if (bmv && bms) {
      bmv.textContent = total > 0 ? okCount + '/' + total + ' passed' : '—';
      bms.textContent = sub || '';
    }
    if (md) {
      if (!total) md.className = 'status-dot';
      else if (okCount === total) md.className = 'status-dot ok';
      else md.className = 'status-dot bad';
    }
    if (fSt) fSt.textContent = total > 0 ? okCount + '/' + total : '—';
    if (fLn) fLn.textContent = sub || '';
  }

  if (list) {
    fetch('/api/module-board')
      .then(function (r) {
        return r.json();
      })
      .then(function (j) {
        if (!j || !j.ok) {
          list.innerHTML = '<p class="caps pg-module-board-msg">Could not load module board.</p>';
          setModuleBannerEarly(0, 0, 'Module API unavailable');
          return;
        }
        var mods = j.modules || [];
        if (!mods.length) {
          list.innerHTML = '<p class="caps pg-module-board-msg">No modules.</p>';
          setModuleBannerEarly(0, 0, 'No rows');
          return;
        }
        var okCount = 0;
        for (var mi = 0; mi < mods.length; mi++) {
          if (mods[mi].ok) okCount++;
        }
        var bad = mods.length - okCount;
        var sub =
          bad === 0
            ? 'All wiring checks passed'
            : okCount + ' passed · ' + bad + ' not wired / not armed';
        setModuleBannerEarly(okCount, mods.length, sub);
        list.innerHTML = '';
        for (var i = 0; i < mods.length; i++) {
          var m = mods[i];
          var row = document.createElement('div');
          row.className = 'pg-status-item';
          row.setAttribute('role', 'button');
          row.setAttribute('tabindex', '0');
          var det2 = m.detail != null ? String(m.detail) : '';
          row.innerHTML =
            '<span class="status-dot ' +
            (m.ok ? 'ok' : 'bad') +
            '" title="' +
            esc(det2.slice(0, 500)) +
            '"></span>' +
            '<div><div class="pg-status-name">' +
            esc(m.label || m.id || '—') +
            '</div>' +
            '<div class="pg-status-meta">' +
            esc(det2.slice(0, 280)) +
            '</div></div>';
          list.appendChild(row);
        }
      })
      .catch(function (e) {
        list.innerHTML =
          '<p class="caps pg-module-board-msg">' + esc(String(e && e.message ? e.message : e)) + '</p>';
        setModuleBannerEarly(0, 0, 'Fetch failed');
        if (md) md.className = 'status-dot bad';
      });
  }
})();
