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

  var gt = document.getElementById('groundhogText');
  var gv = document.getElementById('groundhogV');
  var ghTile = document.getElementById('groundhogBannerTile');
  function ghHeadline(j) {
    var sig = j.wiring_signal;
    if (sig === 'green') return 'Ready';
    if (sig === 'yellow') return j.env_enabled ? 'Wait' : 'Off';
    if (sig === 'red') return 'Fault';
    return j.env_enabled ? 'Wait' : 'Off';
  }
  function ghTileClass(sig) {
    if (!ghTile) return;
    ghTile.classList.remove('gh-sig-green', 'gh-sig-yellow', 'gh-sig-red');
    if (sig === 'green') ghTile.classList.add('gh-sig-green');
    else if (sig === 'yellow') ghTile.classList.add('gh-sig-yellow');
    else if (sig === 'red') ghTile.classList.add('gh-sig-red');
  }
  fetch('/api/groundhog-memory')
    .then(function (r) {
      return r.json();
    })
    .then(function (j) {
      if (!gt) return;
      if (!j || !j.ok) {
        gt.textContent = '—';
        if (gv) gv.textContent = '—';
        ghTileClass('red');
        if (ghTile) ghTile.title = 'Groundhog status unavailable';
        return;
      }
      var sig = j.wiring_signal || 'yellow';
      ghTileClass(sig);
      if (gv) gv.textContent = ghHeadline(j);
      var ap =
        j.bundle && j.bundle.apply
          ? String(j.bundle.apply.atr_stop_mult) + ' / ' + String(j.bundle.apply.atr_target_mult)
          : '—';
      gt.textContent = sig === 'green' && ap !== '—' ? ap : '—';
      if (ghTile) {
        var tip = (j.wiring_detail || '') + '\n\n' + 'Canonical: ' + (j.path || '—');
        if (j.env_enabled !== undefined) {
          tip += '\nMerge env: ' + (j.env_enabled ? 'on' : 'off');
        }
        ghTile.title = tip.trim();
      }
    })
    .catch(function (e) {
      if (gt) gt.textContent = '—';
      if (gv) gv.textContent = '—';
      ghTileClass('red');
      if (ghTile) ghTile.title = e && e.message ? e.message : String(e);
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
          var det = m.detail != null ? String(m.detail) : '';
          row.innerHTML =
            '<span class="status-dot ' +
            (m.ok ? 'ok' : 'bad') +
            '" title="' +
            esc(det.slice(0, 500)) +
            '"></span>' +
            '<div><div class="pg-status-name">' +
            esc(m.label || m.id || '—') +
            '</div>' +
            '<div class="pg-status-meta">' +
            esc(det.slice(0, 280)) +
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
