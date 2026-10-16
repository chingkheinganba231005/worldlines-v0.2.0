'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const state = {data: null, index: 0, reference: 'frozen', metric: 'displacement', range: 'all', timer: null, tab: 'observatory', real: null, realPage: 0};
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number = (v, digits=3) => typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '—';
  const percent = v => typeof v === 'number' && Number.isFinite(v) ? (100*v).toFixed(1)+'%' : '—';
  const shortDate = date => new Date(date+'T12:00:00Z').toLocaleDateString('en-GB',{day:'2-digit',month:'short',timeZone:'UTC'});
  const fullDate = date => new Date(date+'T12:00:00Z').toLocaleDateString('en-GB',{day:'2-digit',month:'long',year:'numeric',timeZone:'UTC'});
  function switchTab(tab) {
    if (!['observatory','methodology','events','real-data'].includes(tab)) return;
    state.tab=tab;
    if(tab==='real-data' && !state.real)loadReal();
    document.querySelectorAll('.page-panel').forEach(el => el.hidden = el.id !== tab);
    document.querySelectorAll('.nav-tab').forEach(el => { const active=el.dataset.tab===tab; el.classList.toggle('active',active); if(active) el.setAttribute('aria-current','page'); else el.removeAttribute('aria-current'); });
    if(tab!=='observatory') stopReplay();
    history.replaceState(null,'','#'+tab);
    window.scrollTo({top:0,behavior:reducedMotion?'auto':'smooth'});
  }
  function current() { return state.data.history[state.index]; }
  function metric(row) { return state.metric==='surprise' ? row.surprise_percentile : state.reference==='rolling' ? row.rolling_js : row.js_topic; }
  function setIndex(index) {state.index=Math.max(0,Math.min(state.data.history.length-1,Number(index))); render();}
  function stopReplay() {clearInterval(state.timer);state.timer=null;$('play').textContent='▶ Replay';$('play').setAttribute('aria-pressed','false');}
  function referenceShares(row) {
    if(state.reference==='frozen') return row.reference_shares;
    return row.rolling_reference_shares || null;
  }
  function render() {
    const row=current();
    $('selected-date').textContent=fullDate(row.date);
    $('phase').textContent=String(row.phase).toUpperCase();
    $('reference-detail').textContent=(state.reference==='frozen'?'Reference: frozen training distribution':'Reference: preceding 30 comparable windows')+(state.reference==='frozen'&&row.reference_end ? ' · through '+row.reference_end : ' · excludes selected day');
    const js=state.reference==='frozen'?row.js_topic:row.rolling_js;
    const transport=state.reference==='frozen'?row.transport_cost:row.rolling_transport;
    $('displacement').textContent=number(js,4);
    $('transport').textContent='OT '+number(transport,4);
    const available=typeof row.surprise_percentile==='number' && Number.isFinite(row.surprise_percentile);
    $('surprise').innerHTML=available ? number(row.surprise_percentile,1)+'<small>/ 100</small>' : '—';
    $('surprise-label').textContent=available?'Descriptive historical rank':'Awaiting sufficient prior observations';
    $('calibration-note').textContent=available?`${row.calibration_n ?? 0} prior scores · descriptive only`:'No supported surprise estimate';
    $('surprise-label').title=row.forecast_train_through?'Forecast uses data through '+row.forecast_train_through:'Forecast unavailable';
    const warnings=Array.isArray(row.coverage_warnings)?row.coverage_warnings:[];
    $('coverage').classList.toggle('warning',!row.coverage_ok);
    $('coverage').innerHTML=`<strong><span class="dot"></span>${row.coverage_ok?'Coverage check passed':'Coverage warning'}</strong><span>${escapeHTML(row.unique_events)} simulated events</span><span>${escapeHTML(row.raw_mentions)} raw mentions</span><span>${escapeHTML(row.source_count)} synthetic sources</span><span>Source JSD ${number(row.source_js)}</span>${warnings.length?'<span class="coverage-break">'+warnings.map(escapeHTML).join(' · ')+'</span>':''}`;
    $('date-slider').value=String(state.index);
    $('date-slider').setAttribute('aria-valuetext',fullDate(row.date));
    $('slider-date').textContent=row.date;
    $('previous').disabled=state.index===0;
    $('next').disabled=state.index===state.data.history.length-1;
    $('event-date').value=String(state.index);
    $('versions').textContent=`MODEL ${state.data.model_version} / DATA ${state.data.data_version} / AS OF ${row.date} / ${String(row.phase).toUpperCase()} WINDOW`;
    renderChart(); renderDomains(); renderEvents(); renderAlerts();
  }
  function renderChart() {
    const historyData=state.data.history;
    const last=historyData.length-1;
    const count=state.range==='all'?historyData.length:Number(state.range);
    // A range ends at the selected day and expands only into earlier history.
    const end=state.range==='all'?last:state.index;
    const start=Math.max(0,end-count+1);
    const rows=historyData.slice(start,end+1);
    const vals=rows.map(metric).filter(v=>typeof v==='number' && Number.isFinite(v));
    const width=1000,height=235,left=47,right=16,top=17,bottom=30;
    const max=state.metric==='surprise'?100:Math.max(.01,...vals)*1.18;
    const X=i=>left+(rows.length<=1?(width-left-right)/2:i/(rows.length-1)*(width-left-right));
    const Y=v=>top+(1-v/max)*(height-top-bottom);
    let svg=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${state.metric==='surprise'?'Descriptive surprise rank':'Jensen–Shannon displacement'} from ${rows[0].date} to ${rows[rows.length-1].date}. Use the date slider below for exact observations."><defs><linearGradient id="chart-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#c6aa5e" stop-opacity=".19"/><stop offset="100%" stop-color="#c6aa5e" stop-opacity="0"/></linearGradient></defs>`;
    for(let t=0;t<=4;t++){const y=top+t*(height-top-bottom)/4;const value=max*(1-t/4);svg+=`<line x1="${left}" x2="${width-right}" y1="${y}" y2="${y}" stroke="#30392b" stroke-width="1"/><text x="${left-10}" y="${y+3}" text-anchor="end" font-size="9" font-family="monospace" fill="#8a967e">${state.metric==='surprise'?value.toFixed(0):value.toFixed(3)}</text>`;}
    const paths=[];let segment=[];
    rows.forEach((r,i)=>{const v=metric(r);if(typeof v==='number' && Number.isFinite(v)) segment.push([X(i),Y(v)]);else if(segment.length){paths.push(segment);segment=[];}});if(segment.length)paths.push(segment);
    paths.forEach(points=>{const d=points.map((p,i)=>(i?'L':'M')+p.map(v=>v.toFixed(2)).join(',')).join(' ');svg+=`<path d="${d} L${points.at(-1)[0]},${height-bottom} L${points[0][0]},${height-bottom} Z" fill="url(#chart-fill)"/><path d="${d}" stroke="#d8b769" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`;if(points.length===1)svg+=`<circle cx="${points[0][0]}" cy="${points[0][1]}" r="3" fill="#e6bd65"/>`;});
    rows.forEach((r,i)=>{if(r.alert && r.alert.state==='candidate'){svg+=`<circle cx="${X(i)}" cy="${height-bottom+1}" r="2" fill="#bdab70"/>`;}});
    const selected=state.index-start;
    if(selected>=0 && selected<rows.length){const x=X(selected),v=metric(rows[selected]);svg+=`<line x1="${x}" x2="${x}" y1="${top}" y2="${height-bottom}" stroke="#b9c0a5" stroke-dasharray="3 5" opacity=".7"/>`;if(typeof v==='number' && Number.isFinite(v))svg+=`<circle cx="${x}" cy="${Y(v)}" r="5" stroke="#e6bd65" stroke-width="2" fill="#1c221b"/><circle cx="${x}" cy="${Y(v)}" r="2" fill="#e6bd65"/>`;}
    const ticks=[...new Set([0,Math.round((rows.length-1)/3),Math.round(2*(rows.length-1)/3),rows.length-1])];ticks.forEach(i=>{svg+=`<text x="${X(i)}" y="${height-6}" text-anchor="middle" font-size="9" font-family="monospace" fill="#8a967e">${escapeHTML(shortDate(rows[i].date))}</text>`;});
    if(!vals.length)svg+=`<text x="500" y="115" text-anchor="middle" font-size="14" font-family="sans-serif" fill="#b1b69f">Insufficient history for this metric in the selected range</text>`;
    svg+='</svg>';
    $('chart').innerHTML=svg;
    $('chart-label').textContent=state.metric==='surprise'?'DESCRIPTIVE RANK / 0–100':'JSD / NATS · '+(state.reference==='frozen'?'FROZEN REFERENCE':'ROLLING REFERENCE');
    $('chart').onclick=event=>{const rect=$('chart').getBoundingClientRect();const relative=((event.clientX-rect.left)/rect.width*width-left)/(width-left-right);setIndex(start+Math.round(Math.max(0,Math.min(1,relative))*(rows.length-1)));};
  }
  function renderDomains() {
    const row=current(),ref=referenceShares(row),shares=row.topic_shares || [];
    const max=Math.max(.01,...shares,...(ref||[]));
    const interval=row.forecast_share_interval_80;
    $('forecast-uncertainty').innerHTML=Array.isArray(interval)&&Array.isArray(row.forecast_shares)?`<p>Forecast uses data through ${escapeHTML(row.forecast_train_through)}. The 80% intervals below are conditional on the model and its assumptions. Their real-world coverage is unvalidated.</p><table><thead><tr><th>Topic</th><th>Forecast</th><th>80% interval</th></tr></thead><tbody>${state.data.taxonomy.map((domain,i)=>`<tr><td>${escapeHTML(domain.label)}</td><td>${percent(row.forecast_shares[i])}</td><td>${percent(interval[0]?.[i])}–${percent(interval[1]?.[i])}</td></tr>`).join('')}</tbody></table>`:'<p>Forecast intervals are unavailable for this observation.</p>';
    $('domain-bars').innerHTML=state.data.taxonomy.map((domain,i)=>`<div class="domain-row"><span class="domain-name">${escapeHTML(domain.label)}</span><div class="bar-track" aria-label="${escapeHTML(domain.label)}: selected ${percent(shares[i])}, reference ${ref?percent(ref[i]):'unavailable'}"><span class="bar" style="width:${(shares[i]||0)/max*100}%"></span>${ref?`<span class="bar reference" style="width:${(ref[i]||0)/max*100}%"></span>`:''}</div><span class="domain-share">${percent(shares[i])}</span></div>`).join('')+(ref?'':'<p class="empty">Rolling reference shares unavailable for this observation.</p>');
  }
  function eventHTML(event,index) {
    const domain=state.data.taxonomy.find(d=>d.id===event.domain);
    return `<button class="event-card" data-event-index="${index}"><span class="event-meta"><span>${escapeHTML(domain?domain.label:event.domain)} / ${escapeHTML(event.region)}</span><span>SYNTHETIC</span></span><h3>${escapeHTML(event.title)}</h3><span class="event-bottom">${escapeHTML(event.source_count)} simulated sources <span aria-hidden="true">·</span> Inspect record ↗</span></button>`;
  }
  function renderEvents() {
    const events=current().events || [];
    $('event-count').textContent=String(events.length).padStart(2,'0');
    $('day-events').innerHTML=events.length?events.slice(0,3).map(eventHTML).join(''):'<p class="empty">No simulated event records in this observation.</p>';
    const filter=$('event-filter').value;
    const filtered=events.map((event,index)=>({event,index})).filter(({event})=>filter==='all'||event.domain===filter);
    $('event-log').innerHTML=filtered.length?filtered.map(({event,index})=>eventHTML(event,index)).join(''):'<p class="empty">No events match this topic on the selected date.</p>';
    document.querySelectorAll('[data-event-index]').forEach(button=>button.onclick=()=>showEvent(events[Number(button.dataset.eventIndex)]));
  }
  function showEvent(event) {
    $('event-details').innerHTML=`<span class="pill">SIMULATED EVIDENCE</span><h2>${escapeHTML(event.title)}</h2><p>${escapeHTML(event.explanation || 'No additional explanation supplied.')}</p><dl><dt>Record ID</dt><dd>${escapeHTML(event.id)}</dd><dt>Observation</dt><dd>${escapeHTML(current().date)}</dd><dt>Topic</dt><dd>${escapeHTML(event.domain)}</dd><dt>Region</dt><dd>${escapeHTML(event.region)}</dd><dt>Sources</dt><dd>${escapeHTML(event.source_count)} simulated sources</dd><dt>Verification</dt><dd>${escapeHTML(event.verification_status)}</dd></dl><div class="notice"><span class="notice-label">NO REAL-WORLD CLAIM</span><p>This event is invented to exercise the pipeline. It has no factual source links and must not be cited as news.</p></div>`;
    $('event-dialog').showModal();
  }
  function renderAlerts() {
    const alerts=state.data.history.slice(0,state.index+1).map((row,index)=>({row,index})).filter(({row})=>row.alert&&['candidate','suppressed','resolved'].includes(row.alert.state)).slice(-5).reverse();
    $('alerts').innerHTML=alerts.length?alerts.map(({row,index})=>`<button class="alert-row" data-alert-index="${index}"><time datetime="${escapeHTML(row.date)}">${escapeHTML(row.date)}</time><span class="pill">${escapeHTML(row.alert.state.toUpperCase())}</span><span>${escapeHTML(row.alert.reason)}</span><span aria-hidden="true">↗</span></button>`).join(''):'<p class="empty">No candidate signals through this observation.</p>';
    document.querySelectorAll('[data-alert-index]').forEach(button=>button.onclick=()=>{stopReplay();setIndex(Number(button.dataset.alertIndex));$('selected-date').scrollIntoView({behavior:reducedMotion?'auto':'smooth',block:'center'});});
  }
  function download(value,filename) {
    const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download=filename;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }

  const safeURL = value => {try {const url=new URL(value);return ['http:','https:'].includes(url.protocol)?url.href:null;}catch{return null;}};
  async function loadReal() {
    $('real-status').textContent='Loading the archive sample…';$('real-status').hidden=false;
    try {
      const response=await fetch('./data/gdelt_sample.json',{cache:'no-cache'});
      if(!response.ok)throw new Error('Archive sample unavailable (HTTP '+response.status+').');
      const data=await response.json();
      if(data.mode!=='historical_sample'||!Array.isArray(data.history))throw new Error('Unsupported archive sample format.');
      state.real=data;state.realPage=0;
      const archives=data.archives||[];const count=data.history.reduce((sum,row)=>sum+(row.events||[]).length,0);
      $('real-stats').innerHTML=`<div class="real-stat"><strong>${count.toLocaleString()}</strong><span>Provisional extracted records</span></div><div class="real-stat"><strong>${archives.length}</strong><span>15-minute archive slots</span></div><div class="real-stat"><strong>—</strong><span>Scores, forecasts, alerts unavailable</span></div>`;
      $('real-date').innerHTML=data.history.map((row,i)=>`<option value="${i}">${escapeHTML(row.date)}</option>`).join('');
      $('real-date').value=String(Math.max(0,data.history.length-1));
      $('real-provenance').textContent=`Retrieved ${data.generated_at || 'unknown'}. Provider data as of ${data.data_as_of || 'unknown'}. ${data.methodology?.sampling || 'Partial historical archive sample.'} ${data.methodology?.deduplication || ''} ${data.methodology?.rights || ''}`;
      $('real-archives').innerHTML=archives.map(archive=>{const url=safeURL(archive.url);return url?`<a href="${escapeHTML(url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(archive.url)} ↗</a>`:'';}).join('');
      $('real-status').hidden=true;$('real-content').hidden=false;renderReal();
    } catch(error) {$('real-status').textContent=error.message+' The synthetic observatory remains available.';}
  }
  function renderReal() {
    if(!state.real)return;
    const day=state.real.history[Number($('real-date').value)];
    const search=$('real-search').value.trim().toLowerCase();
    const events=(day?.events || []).filter(event=>!search||String(event.label).toLowerCase().includes(search));
    const pageSize=15,pages=Math.max(1,Math.ceil(events.length/pageSize));state.realPage=Math.min(state.realPage,pages-1);
    $('real-records').innerHTML=events.length?events.slice(state.realPage*pageSize,(state.realPage+1)*pageSize).map(event=>{
      const url=safeURL(event.source_url || event.source_citation);
      return `<article class="real-record"><div class="record-top"><span>${escapeHTML(event.id)}</span><span class="pill">PROVISIONAL EXTRACTION</span></div><h3>${escapeHTML(event.label)}</h3><p>Occurrence: ${escapeHTML(event.event_time_utc?.slice(0,10)||'Unknown')} · Provider insertion: ${escapeHTML(event.available_at_utc||'Unknown')}</p><p>${escapeHTML((event.credibility_flags||[]).join(' · ').replaceAll('_',' '))}</p>${url?`<a href="${escapeHTML(url)}" target="_blank" rel="noopener noreferrer">Publisher source: ${escapeHTML(event.publisher||new URL(url).hostname)} ↗</a>`:'<p>No usable publisher URL supplied.</p>'}</article>`;
    }).join(''):'<p class="empty">No records match this search in the selected archive date.</p>';
    $('real-page').textContent=`${state.realPage+1} / ${pages} · ${events.length} records`;
    $('real-previous').disabled=state.realPage===0;$('real-next').disabled=state.realPage>=pages-1;
  }
  $('real-date').addEventListener('change',()=>{state.realPage=0;renderReal();});
  $('real-search').addEventListener('input',()=>{state.realPage=0;renderReal();});
  $('real-previous').onclick=()=>{state.realPage=Math.max(0,state.realPage-1);renderReal();};
  $('real-next').onclick=()=>{state.realPage++;renderReal();};
  $('download-real').onclick=()=>download(state.real,'worldline-gdelt-historical-sample.json');

  async function load() {
    $('loading').hidden=false;$('load-error').hidden=true;$('app').hidden=true;
    try {
      const response=await fetch('./data/demo.json',{cache:'no-cache'});
      if(!response.ok)throw new Error(`Dataset request returned HTTP ${response.status}.`);
      const data=await response.json();
      if(data.mode!=='synthetic_demo'||!Array.isArray(data.history)||!data.history.length||!Array.isArray(data.taxonomy))throw new Error('The dataset is missing the expected synthetic-demo structure.');
      state.data=data;state.index=data.history.length-1;
      $('date-slider').max=String(data.history.length-1);
      $('event-date').innerHTML=data.history.map((row,i)=>`<option value="${i}">${escapeHTML(fullDate(row.date))}</option>`).join('');
      $('event-filter').innerHTML='<option value="all">All topics</option>'+data.taxonomy.map(d=>`<option value="${escapeHTML(d.id)}">${escapeHTML(d.label)}</option>`).join('');
      $('method-summary').textContent=data.methodology?.summary || 'WORLDLINE measures changes in a recorded topic distribution, while keeping data coverage and uncertainty visible.';
      $('limitations').innerHTML=(data.methodology?.limitations || []).map(text=>'<li>'+escapeHTML(text)+'</li>').join('');
      $('loading').hidden=true;$('app').hidden=false;render();
      const requested=location.hash.slice(1);if(['methodology','events','real-data'].includes(requested))switchTab(requested);
    } catch(error) {
      $('loading').hidden=true;$('load-error').hidden=false;$('error-description').textContent=error.message+' No substitute data has been generated. Retry after the dataset becomes available.';
    }
  }
  document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=>switchTab(button.dataset.tab)));
  document.querySelectorAll('[data-go]').forEach(button=>button.addEventListener('click',()=>switchTab(button.dataset.go)));
  document.querySelector('.wordmark').addEventListener('click',event=>{event.preventDefault();switchTab('observatory');});
  $('reference').addEventListener('change',event=>{state.reference=event.target.value;render();});
  document.querySelectorAll('[data-metric]').forEach(button=>button.addEventListener('click',()=>{state.metric=button.dataset.metric;document.querySelectorAll('[data-metric]').forEach(b=>{const selected=b===button;b.classList.toggle('selected',selected);b.setAttribute('aria-pressed',String(selected));});renderChart();}));
  document.querySelectorAll('[data-range]').forEach(button=>button.addEventListener('click',()=>{state.range=button.dataset.range;document.querySelectorAll('[data-range]').forEach(b=>{const selected=b===button;b.classList.toggle('selected',selected);b.setAttribute('aria-pressed',String(selected));});renderChart();}));
  $('date-slider').addEventListener('input',event=>{stopReplay();setIndex(event.target.value);});
  $('event-date').addEventListener('change',event=>{stopReplay();setIndex(event.target.value);});
  $('event-filter').addEventListener('change',renderEvents);
  $('previous').onclick=()=>{stopReplay();setIndex(state.index-1);};
  $('next').onclick=()=>{stopReplay();setIndex(state.index+1);};
  $('play').onclick=()=>{if(state.timer){stopReplay();return;}if(state.index===state.data.history.length-1)setIndex(0);$('play').textContent='Ⅱ Pause';$('play').setAttribute('aria-pressed','true');state.timer=setInterval(()=>{if(state.index>=state.data.history.length-1){stopReplay();return;}setIndex(state.index+1);},reducedMotion?1800:650);};
  $('download-snapshot').onclick=()=>download({schema_version:state.data.schema_version,mode:state.data.mode,model_version:state.data.model_version,data_version:state.data.data_version,reference_selected:state.reference,taxonomy:state.data.taxonomy,methodology:state.data.methodology,observation:current()},'worldline-observation-'+current().date+'.json');
  $('download-dataset').onclick=()=>download(state.data,'worldline-synthetic-dataset.json');
  $('close-dialog').onclick=()=>$('event-dialog').close();
  $('event-dialog').addEventListener('click',event=>{if(event.target===$('event-dialog')){const rect=event.target.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)event.target.close();}});
  $('retry').onclick=load;
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stopReplay();});
  load();
})();
