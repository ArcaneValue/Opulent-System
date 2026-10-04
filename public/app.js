'use strict';
// Decorative welcome only: never waits for the network or delays authentication requests.
setTimeout(() => document.querySelector('#splash')?.remove(), 2000);
let state, page = 'Dashboard', preview, installPrompt, updateWorker, demoPaid=0, demoResult=false, demoPenalty=false, setupRequired=false;
const $ = s => document.querySelector(s);
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const currency = value => `${esc(state.settings.currency)} ${(value/100).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}`;
const writable = () => state.user.role !== 'viewer';
const admin = () => state.user.role === 'admin';
const sendingLive = () => !!(state && state.sms_mode === 'live');
const messageTone = s => s === 'delivered' || s === 'simulated' ? 'good' : s === 'failed' ? 'bad' : s === 'unknown' || s === 'cancelled' ? 'warn' : '';
const button = (action, label, primary=false, extra='') => `<button data-action="${action}" class="${primary?'primary':''}" ${extra}>${label}</button>`;
const badge = (label, tone='') => `<span class="badge ${tone}">${esc(label)}</span>`;
const empty = (title, detail) => `<div class="empty"><h3>${title}</h3>${detail}</div>`;
function table(headings, records, render, className='') { return records.length ? `<div class="table-wrap"><table class="${className}"><thead><tr>${headings.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${records.map(render).join('')}</tbody></table></div>` : empty('No records yet','Add your first record to get started.'); }
function tr(cells) { return `<tr>${cells.map(c=>`<td>${c}</td>`).join('')}</tr>`; }
function panel(title, body, action='') { return `<section class="panel"><div class="panel-head"><h2>${title}</h2>${action}</div>${body}</section>`; }
function toast(message) { $('#toast').textContent=message; $('#toast').style.display='block'; clearTimeout(toast.timer); toast.timer=setTimeout(()=>$('#toast').style.display='none',6000); }
async function api(route, body) {
  let response;
  try { response = await fetch('/api/'+route, {method:body?'POST':'GET',headers:body?{'Content-Type':'application/json','X-CSRF-Token':state?.user.csrf || ''}:{},body:body?JSON.stringify(body):undefined}); }
  catch { throw Error('Cannot reach Opulent. Start the server and reconnect. Your changes were not confirmed.'); }
  const result=await response.json();
  if(!response.ok) { if(response.status===401 && state){state=null;authScreen('signin');} throw Error(result.error || 'Operation failed.'); }
  return result;
}
async function reload(){state=await api('state'); render();}
async function boot(){try{const status=await api('status');setupRequired=!!status.setup_required;if(status.setup_required)authScreen('signup');else{try{await reload();}catch{authScreen('signin');}}}catch(e){$('#app').innerHTML=panel('Unable to open Opulent', `<p>${esc(e.message)}</p>${button('reload','Try again')}`);}}
function authScreen(mode){
  const signup=mode==='signup';
  const title=signup?(setupRequired?'Welcome to Opulent':'Create your account'):'Welcome back';
  const blurb=signup?(setupRequired?'Create your administrator account. No default password is provided.':'Create your administrator account to use Opulent.'):'Sign in to your staff workspace.';
  const switchLink=signup
    ?'<p class="muted">Already have an account? <button type="button" data-action="auth-signin" style="background:none;border:0;color:#07878c;font-weight:600;text-decoration:underline;padding:0;cursor:pointer">Sign in</button></p>'
    :'<p class="muted">New to Opulent? <button type="button" data-action="auth-signup" style="background:none;border:0;color:#07878c;font-weight:600;text-decoration:underline;padding:0;cursor:pointer">Create a staff account</button></p>';
  $('#app').innerHTML=`<main class="login panel"><div class="brand">OPULENT<small>Property management</small></div><h1>${title}</h1><p class="muted">${blurb}</p><form id="auth" class="form">${signup?field('name','Your name','text','',true):''}${field('email','Staff email','email','',true)}${field('password','Password (at least 12 characters)','password','',true)}<label class="check"><input type="checkbox" data-action="toggle-password"> Show password</label><div class="full">${button('none',signup?'Create administrator account':'Sign in',true,'type="submit"')}<div class="error" id="auth-error"></div></div></form>${switchLink}<div class="hint">Staff access only. Condominium reminders are delivered to clients by SMS.</div></main>`;
  $('#auth').addEventListener('submit',async e=>{e.preventDefault();const submit=e.target.querySelector('button');submit.disabled=true;try{await api(signup?'register':'login',Object.fromEntries(new FormData(e.target)));await reload();}catch(err){$('#auth-error').textContent=err.message;}finally{submit.disabled=false;}});
}
const navigation=[['Dashboard','◈'],['Properties & Units','▤'],['Contacts','♙'],['Charges','▣'],['Payments','▧'],['Reminders','♧'],['Reports','▥'],['Statements','▦'],['Settings','⚙'],['Guided Demo','▷'],['User Guide','?']];
function render(){
  const subtitles={'Dashboard':'Your billing and reminder workspace','Properties & Units':'Manage buildings and the units within them','Contacts':'Tenants and owners · multiple contacts per unit','Charges':'Condominium fees, rent and historical balances','Payments':'Record payments, inspect credit and reverse mistakes','Reminders':sendingLive()?'Preview and send reminders by SMS':'Preview reminders · test mode (no SMS)','Reports':'Balances, exports and administrative audit history','Statements':'A printable charge and payment statement for one unit','Settings':'Staff access, billing preferences and reminder timing','Guided Demo':'Follow one fictional account from registration to an overdue reminder','User Guide':'A practical guide to using your system'};
  $('#app').innerHTML=`<div class="shell"><aside class="sidebar"><div class="brand">OPULENT<small>Property management</small></div><nav class="nav" aria-label="Main navigation">${navigation.map(([name,symbol])=>`<button data-page="${name}" class="${page===name?'active':''}" ${page===name?'aria-current="page"':''}><span class="symbol">${symbol}</span>${name}</button>`).join('')}</nav><div class="sidebar-foot">Staff access only<br>Clients receive SMS<br>Auto-refreshes every 5 min<br>Version ${esc(state.version)}</div></aside><main class="main"><header class="topbar"><span class="mode">${sendingLive()?'LIVE SMS · REAL TEXTS SENT':'TEST MODE · NO SMS SENT'}</span><div class="identity"><span>${esc(state.user.name)} · ${esc(state.user.role)}</span>${button('logout','Sign out')}</div></header><div class="content"><div class="heading"><div><h1>${page}</h1><div class="muted">${subtitles[page]}</div></div><div class="actions">${headingActions()}</div></div>${body()}</div></main></div>`;
  if(page==='Charges') updateCharges();
  if(page==='Reminders') updateReminderSelection();
  if(page==='Statements') bindStatement();
}
function headingActions(){
  const help = tutorials[page] ? button('help','? Help') : '';
  if(page==='User Guide') return button('install','Install on this PC');
  if(page==='Reports') return '<a class="button" href="/api/export" download="opulent-balances.csv">Export balances</a>' + help;
  if(!writable())return badge('Read-only access') + help;
  return ({'Dashboard':button('payment','Record payment',true)+button('reminders','Preview reminders'),'Properties & Units':button('property','Add property')+button('unit','Add unit',true),'Contacts':button('contact','Register contact',true),'Charges':button('plan','Set recurring fee')+button('charge','Add charge',true),'Payments':button('payment','Record payment',true),'Reminders':button('preview','Preview selected',true),'Settings':admin()?button('staff','Add staff'):''}[page] || '') + help;
}
function body(){return {'Dashboard':dashboard,'Properties & Units':properties,'Contacts':contacts,'Charges':charges,'Payments':payments,'Reminders':reminders,'Reports':reports,'Statements':statements,'Settings':preferences,'Guided Demo':guidedDemo,'User Guide':guide}[page]();}
function chargeStatus(ch){return ch.remaining===0?badge('Paid','good'):ch.due<state.today?badge('Overdue','bad'):badge('Outstanding','warn');}
function chargeRow(ch,checkbox=false){return tr([...(checkbox?[`<input type="checkbox" name="charge" value="${ch.id}" aria-label="Select ${esc(ch.unit)} ${esc(ch.type)} ${esc(ch.period)}">`]:[]),`${esc(ch.unit)}<div class="small muted">${esc(ch.property)}</div>`,esc(ch.type),esc(ch.period),esc(ch.due),currency(ch.amount),currency(ch.paid),currency(ch.remaining),chargeStatus(ch)]);}
function dashboard(){
  const month=state.today.slice(0,7), monthly=state.charges.filter(c=>c.period===month), total=arr=>arr.reduce((n,c)=>n+c,0);
  const overdue=state.charges.filter(c=>c.remaining>0&&c.due<state.today), attention=state.charges.filter(c=>c.remaining>0).slice(0,8);
  const credit=state.payments.filter(p=>!p.reversed).reduce((n,p)=>n+p.amount-p.allocated,0);
  const cards=[['Billed this month',currency(total(monthly.map(c=>c.amount))),month],['Allocated to this month',currency(total(monthly.map(c=>c.paid))),'Payments applied to current-period charges'],['Total outstanding',currency(total(state.charges.map(c=>c.remaining))),'All billing periods'],['Overdue units',new Set(overdue.map(c=>c.unit_id)).size,'Units with unpaid past-due charges']];
  return `<div class="cards">${cards.map(([label,value,sub])=>`<div class="card"><span>${label}</span><strong>${value}</strong><span class="small">${sub}</span></div>`).join('')}</div><div class="columns"><div>${panel('Accounts requiring attention',table(['Unit','Category','Period','Due','Charge','Paid','Remaining','Status'],attention,c=>chargeRow(c)))}${panel('Start with a dependable record',`<p class="muted">Register your properties and contacts, set recurring fees, then record payments. Reminders use the remaining balance for each charge.</p><div class="actions">${button('guide','Open user guide')}${button('guided-demo','Try the guided demo',true)}</div>`)}</div><div>${panel('Reminder activity',(sendingLive()?['queued','accepted','delivered','failed','unknown','cancelled']:['queued','simulated','cancelled']).map(s=>`<div class="row"><span>${esc(s.charAt(0).toUpperCase()+s.slice(1))}</span><strong>${state.messages.filter(m=>m.status===s).length}</strong></div>`).join('')+'<p class="small muted">Latest 500 attempts. '+(sendingLive()?'Delivery is confirmed by the provider when the message reaches the handset.':'Test mode: no message reaches a phone.')+'</p>')}${panel('Account credit',`<h2>${currency(credit)}</h2><p class="small muted">Unallocated payments automatically cover future charges for the same unit, oldest due date first.</p>`)}</div></div>`;
}
function properties(){return historyPanel('properties')+historyPanel('units');}
function contacts(){return '<div class="hint">Each number is registered against a property and unit. Use <b>Edit</b> on any row to fix a name, number, unit or billing date at any time.</div>'+historyPanel('contacts');}
function filters(prefix){return `<div class="filters">${field(prefix+'period','Billing period','month','',false,false)}${select(prefix+'unit','Unit',[['','All units'],...state.units.map(u=>[u.id,unitName(u)])],false)}${select(prefix+'type','Category',[['','All categories'],...state.types.map(t=>[t.id,t.name])],false)}${select(prefix+'status','Status',[['','All statuses'],['outstanding','Outstanding'],['overdue','Overdue'],['paid','Paid']],false)}${button('filter-'+prefix,'Apply filters')}</div>`;}
function filtered(prefix){let list=state.charges;const v=key=>$('#'+prefix+key)?.value||'';if(v('period'))list=list.filter(c=>c.period===v('period'));if(v('unit'))list=list.filter(c=>c.unit_id===+v('unit'));if(v('type'))list=list.filter(c=>c.type_id===+v('type'));if(v('status')==='outstanding')list=list.filter(c=>c.remaining>0);if(v('status')==='overdue')list=list.filter(c=>c.remaining>0&&c.due<state.today);if(v('status')==='paid')list=list.filter(c=>!c.remaining);return list;}
function charges(){return panel('Charge ledger',filters('c')+'<div id="charge-table"></div>',writable()?button('generate','Generate a billing period'):'')+panel('Recurring fee plans',table(['Unit','Category','Monthly amount','Due day','From','Until','Status',''],state.plans,p=>tr([esc(p.unit),esc(p.type),currency(p.amount),p.due_day,esc(p.start_period),esc(p.end_period||'Ongoing'),badge(p.active?'Active':'Stopped',p.active?'good':''),p.active&&writable()?button('stop-plan','Stop plan',false,`data-id="${p.id}"`):''])))+panel('Charge categories',state.types.map(t=>badge(t.name)).join(' '),writable()?button('type','Add category'):'');}
function updateCharges(){$('#charge-table').innerHTML=table(['Unit','Category','Period','Due','Charge','Paid','Remaining','Status'],filtered('c'),c=>chargeRow(c));}
function sentStatementLabel(row){
  try{const saved=JSON.parse(row.snapshot_json||'{}');if(row.snapshot_json)return saved.unit_label||saved.title||'Statement';}
  catch{}
  return row.statement_unit||row.statement_title||'Statement';
}
const historySources={
  statements:{title:'Statement history',headings:['Sent','Recipient','Statement','Status','Reason','Reference',''],
    records:()=>state.statement_sends||[],date:r=>r.created||'',status:r=>r.status||'',
    search:r=>[r.phone,sentStatementLabel(r),r.detail].join(' '),
    csv:r=>[r.created,r.phone,sentStatementLabel(r),r.status,r.detail||'',r.provider_ref||''],
    render:r=>tr([esc(String(r.created||'').replace('T',' ').slice(0,19)),esc(r.phone),esc(sentStatementLabel(r)),badge(r.status,messageTone(r.status)),`<div class="text-wrap">${esc(r.detail||r.mode||'—')}</div>`,esc(r.provider_ref||'—'),button('st-view-sent','View',false,`data-id="${r.id}"`)])},
  messages:{title:'Message history',headings:['Created','Recipient','Period / message','Status','Mode','Reference'],
    records:()=>state.messages||[],date:r=>r.created||'',status:r=>r.status||'',
    search:r=>[r.phone,r.body,r.status].join(' '),
    csv:r=>[r.created,r.phone,r.body,r.status,r.mode,r.provider_ref||''],
    render:r=>tr([esc(String(r.created||'').replace('T',' ').slice(0,19)),esc(r.phone),`<div class="text-wrap">${esc(r.body)}</div>`,badge(r.status,messageTone(r.status)),esc(r.mode),esc(r.provider_ref||'—')])},
  audit:{title:'Audit history',headings:['Time (UTC)','Staff','Action','Detail'],
    records:()=>state.audit||[],date:r=>r.created||'',status:()=>'',
    search:r=>[r.actor,r.action,r.detail].join(' '),
    csv:r=>[r.created,r.actor,r.action,r.detail],
    render:r=>tr([esc(r.created),esc(r.actor),esc(r.action),`<div class="text-wrap">${esc(r.detail)}</div>`])},
  payments:{title:'Payment history',headings:['Date','Unit','Reference','Received','Allocated','Credit','Status',''],
    records:()=>state.payments||[],date:r=>r.paid_on||'',status:r=>r.reversed?'Reversed':'Recorded',
    search:r=>[r.unit,r.reference,r.paid_on].join(' '),
    csv:r=>[r.paid_on,r.unit,r.reference,(r.amount/100),r.reversed?'Reversed':'Recorded',r.reason||''],
    render:r=>tr([esc(r.paid_on),esc(r.unit),esc(r.reference),currency(r.amount),r.reversed?'—':currency(r.allocated),r.reversed?'—':currency(r.amount-r.allocated),badge(r.reversed?'Reversed':'Recorded',r.reversed?'bad':'good'),!r.reversed&&writable()?button('reverse','Reverse',false,`data-id="${r.id}"`):esc(r.reason||'')])},
  properties:{title:'Properties',headings:['Property','Address','Units'],tableClass:'',
    records:()=>state.properties||[],date:null,status:null,
    search:r=>[r.name,r.address].join(' '),csv:r=>[r.name,r.address],
    render:r=>tr([esc(r.name),esc(r.address),state.units.filter(u=>u.property_id===r.id).length])},
  units:{title:'Units',headings:['Property','Owner','Unit','Contacts','Status','Actions'],tableClass:'row-actions',
    records:()=>state.units||[],date:null,status:r=>r.active?'Active':'Inactive',
    search:r=>[r.property,r.owner,r.label].join(' '),
    csv:r=>[r.property,r.owner||'',r.label,r.active?'Active':'Inactive'],
    render:r=>tr([esc(r.property),esc(r.owner||'—'),esc(r.label),state.contacts.filter(c=>c.unit_id===r.id&&c.active).length,badge(r.active?'Active':'Inactive',r.active?'good':''),writable()?button('unit-toggle',r.active?'Deactivate':'Activate',false,`data-id="${r.id}" class="pill-button"`):''])},
  contacts:{title:'Registered contacts',headings:['Name','Type','Unit','Primary phone','Alternate phone','Billing start','Notifications','Status','Actions'],tableClass:'row-actions',
    records:()=>state.contacts||[],date:null,status:r=>r.active?'Active':'Inactive',
    search:r=>[r.name,r.phone,r.alternate_phone,r.unit].join(' '),
    csv:r=>[r.name,r.kind,r.unit,r.phone,r.alternate_phone||'',r.billing_start||'',r.notify?'Enabled':'Disabled',r.active?'Active':'Inactive'],
    render:r=>tr([esc(r.name),esc(r.kind),esc(r.unit),esc(r.phone),esc(r.alternate_phone||'—'),esc(r.billing_start||'Not recorded'),r.notify?'Enabled':'Disabled',badge(r.active?'Active':'Inactive',r.active?'good':''),writable()?`${button('contact-edit','Edit',true,`data-id="${r.id}"`)} ${button('contact-toggle',r.active?'Deactivate':'Activate',false,`data-id="${r.id}"`)} ${button('notify-toggle',r.notify?'Mute SMS':'Enable SMS',false,`data-id="${r.id}"`)}`:''])},
  balances:{title:'Balances by unit',headings:['Property','Unit','Billed','Paid against charges','Remaining','Unallocated credit'],tableClass:'',
    records:()=>state.units||[],date:null,status:null,
    search:r=>[r.property,r.label].join(' '),
    csv:r=>{const ch=state.charges.filter(c=>c.unit_id===r.id),s=k=>ch.reduce((n,c)=>n+c[k],0),cr=state.payments.filter(p=>p.unit_id===r.id&&!p.reversed).reduce((n,p)=>n+p.amount-p.allocated,0);return [r.property,r.label,(s('amount')/100),(s('paid')/100),(s('remaining')/100),(cr/100)];},
    render:r=>{const ch=state.charges.filter(c=>c.unit_id===r.id),sum=k=>ch.reduce((n,c)=>n+c[k],0),credit=state.payments.filter(p=>p.unit_id===r.id&&!p.reversed).reduce((n,p)=>n+p.amount-p.allocated,0);return tr([esc(r.property),esc(r.label),currency(sum('amount')),currency(sum('paid')),currency(sum('remaining')),currency(credit)]);}}
};
let historyKind='statements';
const historyFilter={from:'',to:'',search:'',status:''};
function historyPanel(kind){
  const spec=historySources[kind],records=spec.records();
  if(!records.length) return panel(spec.title,empty('No records yet','Nothing has been recorded here yet.'));
  const shown=records.slice(0,5);
  const foot=records.length>shown.length?`<div class="history-foot"><span class="small muted">Showing latest ${shown.length} of ${records.length}</span>${button('history-all','View all',false,`data-kind="${kind}"`)}</div>`:'';
  return panel(spec.title,table(spec.headings,shown,spec.render,spec.tableClass||'')+foot);
}
function historyFiltered(kind){
  const spec=historySources[kind];
  let list=spec.records();
  if(spec.date&&historyFilter.from)list=list.filter(r=>String(spec.date(r)).slice(0,10)>=historyFilter.from);
  if(spec.date&&historyFilter.to)list=list.filter(r=>String(spec.date(r)).slice(0,10)<=historyFilter.to);
  if(spec.status&&historyFilter.status)list=list.filter(r=>String(spec.status(r))===historyFilter.status);
  if(historyFilter.search){const q=historyFilter.search.toLowerCase();list=list.filter(r=>String(spec.search(r)).toLowerCase().includes(q));}
  return list;
}
function renderHistory(){
  const spec=historySources[historyKind],list=historyFiltered(historyKind);
  const count=$('#hs-count');
  if(count)count.textContent='Showing '+list.length+' of '+spec.records().length+' record(s).';
  const target=$('#history-list');
  if(target)target.innerHTML=table(spec.headings,list,spec.render);
}
function syncHistoryRange(){const f=$('#hs-from'),t=$('#hs-to');if(f)f.value=historyFilter.from;if(t)t.value=historyFilter.to;}
function setHistoryRange(days){
  const today=new Date(state.today+'T00:00:00Z');
  historyFilter.to=today.toISOString().slice(0,10);
  historyFilter.from=new Date(today.getTime()-(days-1)*86400000).toISOString().slice(0,10);
  syncHistoryRange();renderHistory();
}
function openHistory(kind){
  historyKind=kind;
  const spec=historySources[kind];
  const statuses=spec.status?[...new Set(spec.records().map(r=>spec.status(r)).filter(Boolean))]:[];
  historyFilter.from='';historyFilter.to='';historyFilter.search='';historyFilter.status='';
  const searchBox='<label>Search<input type="text" id="hs-search" placeholder="search…"></label>';
  const statusBox=statuses.length?select('hs-status','Status',[['','All'],...statuses.map(s=>[s,s])],false,''):'';
  const filters=spec.date
    ?`<div class="filters">${button('hs-7','Last 7 days')}${button('hs-30','Last 30 days')}${button('hs-90','Last 3 months')}${button('hs-365','Last 12 months')}${button('hs-all','All time')}</div><div class="filters"><label>From<input type="date" id="hs-from"></label><label>To<input type="date" id="hs-to"></label>${searchBox}${statusBox}</div>`
    :`<div class="filters">${searchBox}${statusBox}</div>`;
  $('#modal').innerHTML=`<header><h2>${esc(spec.title)}</h2><button class="close" data-action="close" aria-label="Close dialog">×</button></header>`
    +filters
    +`<p class="small muted" id="hs-count"></p><div id="history-list"></div>`
    +`<footer>${button('hs-csv','Download CSV')}${button('close','Close',true)}</footer>`;
  $('#modal').showModal();
  const from=$('#hs-from'),to=$('#hs-to'),search=$('#hs-search'),status=$('#hs-status');
  if(from)from.addEventListener('change',()=>{historyFilter.from=from.value;renderHistory();});
  if(to)to.addEventListener('change',()=>{historyFilter.to=to.value;renderHistory();});
  if(search)search.addEventListener('input',()=>{historyFilter.search=search.value;renderHistory();});
  if(status)status.addEventListener('change',()=>{historyFilter.status=status.value;renderHistory();});
  renderHistory();
}
function historyCSV(){
  const spec=historySources[historyKind],list=historyFiltered(historyKind);
  const rows=[spec.headings].concat(list.map(spec.csv));
  const csv=rows.map(row=>row.map(v=>'"'+String(v==null?'':v).replace(/"/g,'""')+'"').join(',')).join('\r\n');
  const blob=new Blob([csv],{type:'text/csv;charset=utf-8'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=historyKind+'-history.csv';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),1000);
}
function payments(){return '<div class="hint">Payments cover the oldest outstanding charges on the selected unit first, across categories. Any excess remains as account credit. Reversing a payment restores its unpaid balances and preserves an audit trail.</div>'+historyPanel('payments');}
function reminders(){return '<div class="hint warning">'+(sendingLive()?'Live sending is ON. Review recipients, periods, text and estimated cost before confirming — these messages go to real phones.':'Test mode: no SMS is sent. Review recipients, periods, text and estimated cost before confirming.')+'</div>'+panel('Select charges to remind',filters('r')+'<div id="reminder-table"></div>',button('select-all','Select outstanding'))+(writable()?panel('Manual notice and recipients',`<label for="penalty">Penalty notice (optional · overdue charges only)<textarea id="penalty" maxlength="300" placeholder="Enter the notice you want staff to communicate"></textarea></label><p class="small muted">This wording is added only to selected charges that are already overdue. It is never added automatically, and it does not deactivate a card or apply a financial penalty.</p>${button('penalty-example','Use elevator-card example')}<label class="check"><input id="include-alternate" type="checkbox">Also notify the registered alternate numbers for this manual reminder</label><p class="small muted">Primary numbers are selected by default. Alternate numbers appear separately in the preview. Automatic reminders use primary numbers only.</p>`):'')+historyPanel('messages')+`<p class="small muted">Automatic reminders: ${state.settings.automatic?'enabled':'disabled'}. The server checks every 15 seconds. ${button('refresh','Refresh status')}</p>`;}
function updateReminderSelection(){$('#reminder-table').innerHTML=table(['','Unit','Category','Period','Due','Charge','Paid','Remaining','Status'],filtered('r').filter(c=>c.remaining>0),c=>chargeRow(c,true));}
function reports(){return historyPanel('balances')+(admin()?historyPanel('audit'):'');}
let statementDraft=null, statementDirty=false, statementSourceUnit=0, statementRecipientPhone='';
function amountText(v){return (v/100).toLocaleString('en-US',{maximumFractionDigits:2});}
function statementLink(token){return location.origin+'/s/'+token;}
function area(name,label,value='',full=true){return `<label class="${full?'full':''}">${label}<textarea id="${name}" name="${name}">${esc(value)}</textarea></label>`;}
function numberOptions(){
  const seen=new Set(),out=[];
  (state.contacts||[]).forEach(c=>{
    [c.phone,c.alternate_phone].forEach(p=>{
      if(p&&!seen.has(p)){seen.add(p);out.push([p,(c.name||'Contact')+(c.unit?' — '+c.unit:'')+' ('+p+')']);}
    });
  });
  return out;
}
function blankStatement(){
  const columns=['Quarter 1\nJan - Mar','Quarter 2\nApr - Jun','Quarter 3\nJul - Sep','Quarter 4\nOct - Dec'];
  const labels=['Expected Payment','Payment received (UGX)','Balance per quarter','Cumulative Amount Due (UGX)'];
  return {id:0,token:'',title:'CONDOMINIUM FEES STATEMENT FOR '+state.today.slice(0,4)+' (Pacific Victorian)',client:'',unit_label:'',monthly_fee:'',period:'',total_received:'',total_due:'',expires:'',
    columns:columns,rows:labels.map(l=>({label:l,cells:columns.map(()=>'')})),
    notes:['Kindly settle the outstanding balance to avoid penalties and service interruptions.','For inquiries, contact the Property Management Office: 0744570620 OR 0770568161'],
    payment:['Direct at Stanbic Bank: A/C No.: 9030026224704, A/C Name: Opulent Properties Ltd.','Flexi Pay. Dial *291# Follow prompt .... Merchant Code: 283797','Mobile Money direct to the Bank: MTN: *165*6*1*2*2 Account No. /AIRTEL *185*7# and follow prompt']};
}
function statementFromRow(s){
  const row=s||{};
  return {id:row.id||0,token:row.token||'',title:row.title||'',client:row.client||'',unit_label:row.unit_label||'',monthly_fee:row.monthly_fee||'',period:row.period||'',total_received:row.total_received||'',total_due:row.total_due||'',expires:row.expires||'',
    columns:JSON.parse(row.columns_json||'[]'),rows:JSON.parse(row.rows_json||'[]'),notes:JSON.parse(row.notes_json||'[]'),payment:JSON.parse(row.payment_json||'[]')};
}
function captureStatement(){
  const d=statementDraft;if(!d)return;
  const val=id=>{const el=$('#'+id);return el?el.value:'';};
  d.title=val('st-title');d.client=val('st-client');d.unit_label=val('st-unit');d.monthly_fee=val('st-fee');d.period=val('st-period');d.total_received=val('st-received');d.total_due=val('st-due');d.expires=val('st-expires');
  d.columns=d.columns.map((c,i)=>val('st-col-'+i));
  d.rows=d.rows.map((r,ri)=>({label:val('st-row-'+ri),cells:d.columns.map((_,ci)=>val('st-cell-'+ri+'-'+ci))}));
  d.notes=val('st-notes').split('\n').map(s=>s.trim()).filter(Boolean);
  d.payment=val('st-payment').split('\n').map(s=>s.trim()).filter(Boolean);
}
function fillFromRecords(){
  captureStatement();
  const unit=state.units.find(u=>u.id===statementSourceUnit);
  if(!unit){toast('Choose a unit to fill from first.');return;}
  const found=String(statementDraft.title||'').match(/\d{4}/);
  const year=found?found[0]:(state.today||'').slice(0,4);
  const charges=state.charges.filter(c=>c.unit_id===unit.id&&String(c.due||'').slice(0,4)===year);
  const quarter=due=>Math.floor((parseInt(String(due||'01').slice(5,7),10)-1)/3);
  const expected=[0,0,0,0],received=[0,0,0,0],remaining=[0,0,0,0],has=[false,false,false,false];
  charges.forEach(c=>{const i=quarter(c.due);has[i]=true;expected[i]+=c.amount;received[i]+=c.paid;remaining[i]+=c.remaining;});
  let running=0;const cumulative=remaining.map(v=>{running+=v;return running;});
  const cell=(values,i)=>has[i]?amountText(values[i]):'N/A';
  statementDraft.columns=['Quarter 1\nJan - Mar','Quarter 2\nApr - Jun','Quarter 3\nJul - Sep','Quarter 4\nOct - Dec'];
  statementDraft.rows=[
    {label:'Expected Payment',cells:expected.map(cell)},
    {label:'Payment received (UGX)',cells:received.map(cell)},
    {label:'Balance per quarter',cells:remaining.map(cell)},
    {label:'Cumulative Amount Due (UGX)',cells:cumulative.map(cell)}];
  const contacts=(state.contacts||[]).filter(c=>+c.unit_id===+unit.id&&+c.active!==0);
  const contact=contacts.find(c=>c.kind==='Tenant'&&c.phone)||contacts.find(c=>c.kind==='Owner'&&c.phone)||contacts.find(c=>c.phone)||contacts[0];
  statementDraft.client=contact?.name||unit.owner||'';
  statementDraft.unit_label=unit.label||'';
  statementRecipientPhone=contact?.phone||'';
  statementDraft.title='CONDOMINIUM FEES STATEMENT FOR '+year+' ('+(unit.property||'Pacific Victorian')+')';
  statementDraft.period='Quarter 1, Quarter 2, Quarter 3, Quarter 4 ('+year+')';
  statementDraft.total_received=amountText(received.reduce((a,b)=>a+b,0));
  statementDraft.total_due=state.settings.currency+' '+amountText(cumulative[3]||0);
  statementDirty=true;
  toast('Filled from '+(unit.property||'')+' '+unit.label+'. Edit anything before saving.');
}
function statementViewMarkup(d){
  const head=d.columns.map(c=>`<th>${esc(c).replace(/\n/g,'<br>')}</th>`).join('');
  const body=d.rows.map(r=>`<tr><th>${esc(r.label)}</th>${r.cells.map(x=>`<td>${esc(x)}</td>`).join('')}</tr>`).join('');
  return `<div class="statement"><div class="brand-dark">OPULENT<small>Unlocking property opportunities</small></div><h1>${esc(d.title)}</h1><div class="f"><span>Client</span><b>${esc(d.client)}</b></div><div class="f"><span>Unit</span><b>${esc(d.unit_label)}</b></div><div class="f"><span>Monthly Condo fee</span><b>${esc(d.monthly_fee)}</b></div><div class="f"><span>Statement Period</span><b>${esc(d.period)}</b></div><div class="f"><span>Total Payment Received</span><b>${esc(d.total_received)}</b></div><div class="f"><span>Total Amount Due</span><b>${esc(d.total_due)}</b></div><table><thead><tr><th></th>${head}</tr></thead><tbody>${body}</tbody></table><div class="notes"><b>NOTES:</b><ol>${d.notes.map(n=>`<li>${esc(n)}</li>`).join('')}</ol><div class="pay">${d.payment.map(p=>`<div>${esc(p)}</div>`).join('')}</div></div></div>`;
}
function previewStatement(){
  $('#modal').innerHTML=`<header><h2>Statement preview</h2><button class="close" data-action="close" aria-label="Close dialog">×</button></header>${statementViewMarkup(statementDraft)}<footer>${button('close','Close')}</footer>`;
  $('#modal').showModal();
}
function viewSentStatement(id){
  const send=(state.statement_sends||[]).find(row=>row.id===+id);
  if(!send){toast('Statement history record not found.');return;}
  const saved=(state.statements||[]).find(row=>row.id===send.statement_id);
  if(!send.snapshot_json&&!saved){toast('The saved statement is no longer available.');return;}
  let statement;
  try{statement=statementFromRow(send.snapshot_json?JSON.parse(send.snapshot_json):saved);}
  catch{toast('This statement could not be opened.');return;}
  const dialog=document.createElement('dialog');
  dialog.className='statement-view-dialog';
  dialog.innerHTML=`<header><h2>Sent statement</h2><button class="close" data-action="close-statement-view" aria-label="Close statement">×</button></header>${send.snapshot_json?'':'<p class="hint warning">This older history record has no saved copy. Showing the current saved statement.</p>'}${statementViewMarkup(statement)}<footer>${button('close-statement-view','Close')}</footer>`;
  dialog.addEventListener('close',()=>dialog.remove(),{once:true});
  document.body.appendChild(dialog);
  dialog.showModal();
}
async function sendStatement(){
  captureStatement();
  const custom=($('#st-custom')?.value||'').trim();
  const phone=custom||($('#st-number')?.value||'');
  if(!phone){toast('Choose a registered number or type one.');return;}
  // Send the fields currently visible in the builder, including a newly edited unit.
  const saved=await api('statement-save',{statement:statementDraft});
  statementDraft.id=saved.id;statementDraft.token=saved.token;statementDirty=false;
  const sent=await api('statement-send',{id:statementDraft.id,phone:phone});
  toast((sent.status==='accepted'||sent.status==='simulated')?('Statement '+sent.status+' to '+sent.phone+'.'):('Could not send to '+sent.phone+' ('+sent.status+'): '+(sent.detail||'no reason given')));
  await reload();
}
function statements(){
  if(!statementDraft) statementDraft=blankStatement();
  const d=statementDraft;
  const head=d.columns.map((c,i)=>`<th><textarea class="cell" id="st-col-${i}" rows="2">${esc(c)}</textarea></th>`).join('');
  const body=d.rows.map((r,ri)=>`<tr><th><input class="cell" id="st-row-${ri}" value="${esc(r.label)}"></th>${d.columns.map((_,ci)=>`<td><input class="cell" id="st-cell-${ri}-${ci}" value="${esc(r.cells[ci]||'')}"></td>`).join('')}</tr>`).join('');
  const source=select('st-source',"Fill from a unit's records",[['','Choose a unit'],...state.units.map(u=>[u.id,unitName(u)])],false,statementSourceUnit||'');
  const builder=panel('Statement builder',
    '<div class="hint">Every field is editable. The default layout is 5 rows by 5 columns. Save to keep it, then send it.</div>'+
    `<div class="filters">${source}${button('st-fill','Refresh from records')}${button('st-new','New statement')}</div>`+
    `<div class="form">${field('st-title','Statement title','text',d.title,true,false)}${field('st-client','Client name','text',d.client,false,false)}${field('st-unit','Unit label','text',d.unit_label,false,false)}${field('st-fee','Monthly condo fee','text',d.monthly_fee,false,false)}${field('st-period','Statement period','text',d.period,false,false)}${field('st-received','Total payment received','text',d.total_received,false,false)}${field('st-due','Total amount due','text',d.total_due,false,false)}${field('st-expires','Link expiry (optional)','date',d.expires,false,false)}</div>`+
    `<div class="statement"><table class="editable"><thead><tr><th>Quarters</th>${head}</tr></thead><tbody>${body}</tbody></table></div>`+
    `<div class="actions">${button('st-add-row','+ Row')}${button('st-add-col','+ Column')}</div>`+
    `<div class="form">${area('st-notes','Notes (one per line)',d.notes.join('\n'))}${area('st-payment','Payment details (one per line)',d.payment.join('\n'))}</div>`,
    button('st-save','Save')+button('st-preview','Preview',true));
  const send=panel('Send this statement',
    `<div class="filters">${select('st-number','Registered numbers',[['','Choose a number'],...numberOptions()],false,statementRecipientPhone)}${field('st-custom','Or a custom number (e.g. 0772 494 627)','text','',false,false)}${button('st-send','Send SMS',true)}</div>`+
    '<p class="small muted">'+(sendingLive()?'The SMS contains a link and is sent to a real phone.':'Test mode: the SMS is recorded but not sent.')+' '+(d.id?('Link: '+esc(statementLink(d.token))):'Save the statement first to create its link.')+'</p>');
  const history=historyPanel('statements');
  return builder+send+history;
}
function bindStatement(){
  const source=$('#st-source');
  if(source)source.addEventListener('change',()=>{statementSourceUnit=+source.value;if(statementSourceUnit){fillFromRecords();render();}});
  const number=$('#st-number');
  if(number)number.addEventListener('change',()=>{statementRecipientPhone=number.value;});
  ['st-title','st-client','st-unit','st-fee','st-period','st-received','st-due','st-expires','st-notes','st-payment'].forEach(id=>{const el=$('#'+id);if(el)el.addEventListener('input',()=>{statementDirty=true;});});
  document.querySelectorAll('.statement .cell').forEach(el=>el.addEventListener('input',()=>{statementDirty=true;}));
}
function autoRefresh(){
  if(!state||document.hidden)return;
  if(swRegistration)swRegistration.update().catch(()=>{});
  if(updatePending){if(safeToRefresh())location.reload();return;}
  if($('#modal').open)return;
  if(document.querySelector('input:focus, textarea:focus, select:focus'))return;
  if(page==='Statements'&&statementDirty)return;
  reload().catch(()=>{});
}
setInterval(autoRefresh, 300000);
function guidedDemo(){
  const dueDate=new Date(state.today+'T12:00:00Z');dueDate.setUTCDate(dueDate.getUTCDate()-20);const due=dueDate.toISOString().slice(0,10),period=due.slice(0,7);
  const notice="Your Pacific Victoria elevator access card may be deactivated under the property's policy if the overdue payment remains unpaid.";
  const message=`Opulent: PV-A01 Condo Fee for ${period}. Charged: ${state.settings.currency} 350,000.00. Paid: ${state.settings.currency} ${(demoPaid/100).toLocaleString('en-US',{minimumFractionDigits:2})}. Remaining: ${state.settings.currency} ${((35000000-demoPaid)/100).toLocaleString('en-US',{minimumFractionDigits:2})}. Due ${due}.`+(demoPenalty?' Notice: '+notice:'');
  return `<div class="hint warning"><strong>Fictional walkthrough · no database changes</strong><br>These examples live only in this browser session. Payments, notices and simulations here never modify your accounts or contact a phone.</div><div class="cards"><div class="card"><span>Example unit</span><strong>PV-A01</strong><span class="small">Pacific Victoria (fictional account)</span></div><div class="card"><span>Billed</span><strong>${currency(35000000)}</strong><span class="small">${period} condominium fee</span></div><div class="card"><span>Payment recorded</span><strong>${currency(demoPaid)}</strong><span class="small">Click the example payment below</span></div><div class="card"><span>Remaining</span><strong>${currency(35000000-demoPaid)}</strong><span class="small">Overdue · due ${due}</span></div></div><div class="columns"><div>${panel('1 · Register a tenant',`<div class="row"><span>Name / type</span><b>Alex Demo · Tenant</b></div><div class="row"><span>Unit</span><b>PV-A01</b></div><div class="row"><span>Primary phone</span><b>+256700000001</b></div><div class="row"><span>Alternate phone</span><b>+256700000002</b></div><div class="row"><span>Billing started</span><b>17 May 2025</b></div><p class="small muted">The date records when billing began. It does not create historical fees. Contacts → Register contact is the real workflow.</p>`)}${panel('2 · Create a charge and record a payment',`<p>A ${currency(35000000)} charge is due on ${due}. A partial payment reduces this charge; the unpaid portion stays outstanding.</p><div class="actions">${button('demo-pay',demoPaid?'Example payment recorded':'Try a 200,000 example payment',true)}${button('demo-reset','Reset walkthrough')}</div><p class="small muted">Charges records what is owed. Payments records what was received. This example payment updates the cards above without saving a real payment.</p>`)}${panel('3 · Choose the manual notice',`<p>Staff choose the wording when preparing a reminder for an overdue account. The optional notice below is an example, not a declaration that a card has been deactivated.</p>${button('demo-penalty',demoPenalty?'Demo penalty notice included':'Add the elevator-card example')}<p class="small muted">Real reminders → Manual notice and recipients. Automatic reminders never add this notice.</p>`)}</div><div>${panel('4 · Review the SMS',`<div class="preview-card"><strong>Alex Demo</strong><div class="small muted">Primary · +256700000001</div><p>${esc(message)}</p></div><p class="small muted">In the real workflow, the preview also shows estimated segments and cost, with separate entries for alternate numbers if selected.</p>${button('demo-simulate','Run demo simulation',true)}${demoResult?'<div class="hint"><strong>Simulated · DEMO-ONLY</strong><br>This demonstrates the outcome. No SMS or database job was created.</div>':''}`)}${panel('What makes phone delivery real?',`<p class="small">The server prepares and checks the message. An SMS provider must then accept it and return delivery reports. That transport is not connected yet.</p><p class="small muted">Hosting keeps the server running when laptops are off; it does not activate SMS by itself.</p>`)}</div></div>`;
}
function preferences(){const s=state.settings;return panel('Organization and reminders',`<div class="row"><span>Currency / country</span><b>${esc(s.currency)} / ${esc(s.country)}</b></div><div class="row"><span>Timezone offset</span><b>UTC ${s.utc_offset>=0?'+':''}${s.utc_offset/60} hours (fixed offset)</b></div><div class="row"><span>Automatic reminders and current-month billing</span><b>${s.automatic?'Enabled':'Disabled'}</b></div><div class="row"><span>First reminder</span><b>${s.lead_days} days before due date</b></div><div class="row"><span>Overdue repeat interval</span><b>${s.repeat_days} days</b></div><div class="row"><span>Quiet hours for automatic reminders</span><b>${s.quiet_start}:00–${s.quiet_end}:00</b></div><div class="row"><span>Estimated price per segment</span><b>${currency(s.segment_price)}</b></div><p class="small muted">Automatic scheduling runs only while the server and reminder worker are running. Reminders run before the due date, on the due date, then at the overdue interval. Missed send dates are not replayed. ${sendingLive()?'Live SMS sending is enabled through the configured provider.':'Live SMS sending is not enabled; reminders are test mode only.'}</p>`,admin()?button('settings','Edit settings'):'')+(admin()?panel('Staff accounts',table(['Name','Email','Role'],state.staff,u=>tr([esc(u.name),esc(u.email),esc(u.role)]))):'')+panel('Account security',`<p class="muted">Changing your password signs out every session for your account.</p>${button('password','Change my password')}`)+(admin()?panel('Backups',state.database_engine==='postgresql'?`<p>Production backups are managed by Railway PostgreSQL. Verify a scheduled backup and practise restoration before entering real records.</p>`:`<p>Save a verified database backup in the project’s <b>backups</b> folder. Copy it to secure separate storage.</p><p class="small muted">Backups contain personal records and password hashes. Keep them private. Restore instructions are in USER_GUIDE.md.</p>${button('backup','Create backup',true)}`):'');}
const tutorials={
'Dashboard':{intro:'Your starting point: it summarises billing and shows the accounts that need attention.',tasks:[['See the headline numbers','The four cards show what was billed this month, what has been allocated to it, the total still outstanding across all periods, and how many units are overdue.'],['Find who owes money','“Accounts requiring attention” lists unpaid charges, oldest first. Open Payments to record money received.'],['Jump to reminders','Use Record payment or Preview reminders at the top of the page.']],tips:['Money received but not yet used against a charge appears as Account credit.','“Reminder activity” counts messages by status. When live sending is on you will see queued, accepted, delivered, failed and unknown.']},
'Properties & Units':{intro:'Buildings are properties; each unit (for example Block A / A01) is what you bill and what carries a balance.',tasks:[['Add a property','Click Add property and enter its name and the address or location.'],['Add a unit','Click Add unit, choose the property, then a block and a unit label. The combination of property, block and label must be unique.'],['Stop billing a unit','Use Deactivate. Its history stays, but future automatic charges and reminders skip it.']],tips:['Balances belong to the unit, not to a person.','The same unit label can be reused under a different block.']},
'Contacts':{intro:'Contacts are the people who receive reminders for a unit: tenants and owners, with their phone numbers.',tasks:[['Register someone','Click Register contact. Choose the property from the list, then type the unit (a unit that does not exist yet is created automatically), Tenant or Owner, the name, a full international phone number starting with +, and whether they receive reminders.'],['Add a second number','Enter the optional alternate phone. Alternate numbers are used only when you tick “Also notify the registered alternate numbers” on a manual reminder.'],['Stop messages for one person','Use Mute SMS. Use Deactivate when they leave the unit.'],['Correct details','Use Edit to fix the property, unit, name, number or the billing start date.']],tips:['A property is required — a number is always registered against a unit.','A newly typed unit appears straight away in Charges, Reminders and Statements.','Two people can share a phone number; their accounts stay separate.']},
'Charges':{intro:'Charges are what each unit owes. A recurring fee makes the same amount reappear each month; a single charge records a one-off or historical amount.',tasks:[['Set a monthly fee','Click Set recurring fee: choose the unit, the category (Condo Fee or Rent), the monthly amount, the due day and the first period.'],['Create the bills','Click Generate a billing period and pick the month. Running the same month again never duplicates a charge.'],['Add a past amount or arrears','Click Add charge and enter the original period, due date, amount and a reason.'],['Change a future fee','Stop plan, then create a new plan with the new amount and start month. Existing charges are kept.']],tips:['One charge per unit, category and month. Use a second category for a second same-month charge.','A due day of 31 uses the month’s last day in shorter months.','The system does not edit or void a charge that is already billed — check the amount before saving.']},
'Payments':{intro:'Record money you have received. Payments cover a unit’s oldest unpaid charges first, across all categories.',tasks:[['Record a payment','Click Record payment: choose the unit, the amount, the date received and a receipt or bank reference.'],['Understand allocation','The amount is applied oldest due date first. Anything left over stays as account credit and covers future charges.'],['Fix a mistake','Click Reverse, give a reason and save. The original entry stays in history; record the correct payment separately.']],tips:['Future payment dates are rejected.','After a connection error, retry the same form — a brand-new form could create a duplicate entry.']},
'Reminders':{intro:'Preview and then send payment reminders to the contacts of unpaid charges.',tasks:[['Choose who to remind','Filter by month, unit, category or overdue, then tick the charges, or click Select outstanding.'],['Add your own wording','Type a notice in “Penalty notice” to add your own sentence to overdue charges (up to 300 characters).'],['Send','Click Preview selected, review each recipient, number, message and estimated cost, then confirm.'],['Check the result','Click Refresh status after about 15 seconds. Message history shows each attempt and its status.']],tips:['Automatic reminders always use primary numbers only; alternate numbers are manual-only.','If a balance or contact changes after preview, confirmation is refused — preview again.','Status meanings: accepted = the provider took the message; delivered = the handset received it; failed and unknown need attention.']},
'Reports':{intro:'Balances by unit, plus the audit history for administrators.',tasks:[['See balances per unit','“Balances by unit” shows billed, paid against charges, remaining and any unallocated credit.'],['Export to a spreadsheet','Click Export balances to download a CSV you can open in Excel.'],['Review activity','Administrators see the latest 200 audit events: who did what, and when.']],tips:['Remaining is always derived from charges minus non-reversed allocations, so it stays current.']},
'Statements':{intro:'Build a statement, send it by SMS as a link, and keep a history of what you sent.',tasks:[['Choose or build','Start a new statement or select a unit. Every field and table cell is editable.'],['Fill from records (optional)','Selecting a unit fills its client name, unit label, quarterly charges and payments, and registered phone when available. Use Refresh from records to recalculate after changes.'],['Save and preview','Click Save to keep it, and Preview to see exactly what the tenant will see, including the unit.'],['Send','Check the selected registered number (or type one like 0772 494 627) and press Send SMS. The tenant gets a link that opens the statement in any browser.'],['Check the history','The Statement history table lists every send. Click View to read the complete statement as it was when sent.']],tips:['The link works in any browser and needs no login for the tenant.','The View button opens a read-only copy of the sent statement.','Links are permanent unless you set an expiry date.']},
'Settings':{intro:'Organisation preferences, reminder timing, staff accounts, your password and backups.',tasks:[['Set currency and timezone','Edit settings: currency, country, UTC offset and the price per SMS segment.'],['Turn automation on or off','“Automatic billing + reminders” controls whether the server sends on a schedule. Off means you send manually.'],['Choose reminder timing','Days before the due date, the overdue repeat interval, and quiet hours when nothing is sent automatically.'],['Add a staff member','Click Add staff, choose a role and an initial password.'],['Change your password','Click Change my password. This signs out all of your sessions.']],tips:['Currency is locked once financial records exist.','Automatic reminders use primary numbers only and skip quiet hours.','For the hosted system, database backups are managed by the hosting platform.']}
};
function openHelp(page){
  const t=tutorials[page],dialog=$('#modal');
  if(!t){dialog.innerHTML=`<header><h2>Help</h2><button class="close" data-action="close" aria-label="Close dialog">×</button></header><p>No page-specific help is available yet.</p><footer>${button('close','Close')}</footer>`;dialog.showModal();return;}
  dialog.innerHTML=`<header><h2>How to use: ${esc(page)}</h2><button class="close" data-action="close" aria-label="Close dialog">×</button></header><div class="hint">${esc(t.intro)}</div>${t.tasks.map(([q,a])=>`<div class="step"><b>${esc(q)}</b><p>${esc(a)}</p></div>`).join('')}${t.tips&&t.tips.length?`<div class="hint"><b>Good to know</b><br>${t.tips.map(x=>'• '+esc(x)).join('<br>')}</div>`:''}<footer>${button('close','Close')}</footer>`;
  dialog.showModal();
}
function guide(){return panel('Tutorials · step-by-step help',`<p class="muted">Open a short walkthrough for any screen. You can also use the <b>? Help</b> button at the top of each page.</p><div class="actions">${Object.keys(tutorials).map(p=>button('help-page',p,false,`data-page="${p}"`)).join(' ')}</div>`)+panel('Start and access',`<div class="step"><b>1. Open Opulent</b><p>Open the Opulent web address in Microsoft Edge and sign in with your staff account. The hosted system runs continuously — you do not start or keep a server running on your PC.</p></div><div class="step"><b>2. Register a property and unit</b><p>Open Properties &amp; Units → Add property, then Add unit. Use a block name and unique unit label.</p></div><div class="step"><b>3. Register tenants and owners</b><p>Open Contacts → Register contact. Select the unit, name and type. Use a full international phone number beginning with +. Enter the optional alternate phone number and the exact billing-start date, including historical dates. Use Edit to complete older contacts. Deactivate old occupants.</p></div><div class="step"><b>4. Declare rent or condo fees</b><p>Open Charges → Set recurring fee. Choose Rent or Condo Fee, enter the monthly amount, due day and start period. Generate a billing period to create charges immediately. Historical amounts can be entered through Add charge, with their original period and due date.</p></div><div class="step"><b>5. Record payments</b><p>Open Payments → Record payment. Enter the unit, amount, received date and receipt or bank reference. Check the allocations and remaining balances. Reverse incorrect entries with an explanation, then enter the corrected payment.</p></div><div class="step"><b>6. Send reminders</b><p>Open Reminders, select outstanding charges and choose Preview selected. Optionally add a manual notice for overdue charges and include alternate numbers. Review recipients, periods, wording and cost, then confirm. ${sendingLive()?'The provider sends the SMS and the message history confirms delivery. Refresh after 15 seconds.':'In test mode no SMS is sent; the status shows the test completed.'}</p></div><div class="step"><b>7. Install the PC shortcut</b><p>In Microsoft Edge open the menu (…) → Apps → Install this site as an app, or use the button below when your browser offers it. It adds a shortcut that opens Opulent in its own window.</p>${button('install','Install on this PC')}</div><div class="step"><b>8. Automatic scheduling and backups</b><p>Administrators can enable automatic reminders in Settings and choose quiet hours. Reminders run on the hosted server even when your PC is off. Backups are managed by the hosting platform; verify a scheduled backup before entering real records.</p></div><p class="small muted">The complete guide is USER_GUIDE.md in the project folder, including backup restoration, updates and phone-testing limitations.</p>`);}

function field(name,label,type='text',value='',full=false,required=true){return `<label class="${full?'full':''}">${label}<input id="${name}" name="${name}" type="${type}" ${type==='password'?'class="pw" ':''}value="${esc(value)}" ${required?'required':''} ${type==='password'?'minlength="12" maxlength="200" autocomplete="new-password"':''} ${type==='number'?'min="0.01" step="0.01" max="1000000000000"':''}></label>`;}
function select(name,label,options,required=true,value=''){return `<label>${label}<select id="${name}" name="${name}" ${required?'required':''}>${options.map(([id,label])=>`<option value="${esc(id)}" ${String(id)===String(value)?'selected':''}>${esc(label)}</option>`).join('')}</select></label>`;}
function unitSelect(value=''){return select('unit_id','Unit',state.units.filter(u=>u.active||u.id===value).map(u=>[u.id,unitName(u)]),true,value);}
function propertySelect(value=''){return select('property_id','Property',state.properties.map(p=>[p.id,p.name]),true,value);}
function unitLabelField(value=''){return `<label>Unit<input id="unit_label" name="unit_label" list="unit-options" value="${esc(value)}" required autocomplete="off" placeholder="Type a unit, e.g. A303"><datalist id="unit-options"></datalist></label>`;}
function bindUnitOptions(){
  const property=$('#property_id'), list=$('#unit-options');
  if(!property||!list)return;
  const fill=()=>{list.innerHTML=state.units.filter(u=>u.property_id===+property.value).map(u=>`<option value="${esc(u.label)}"></option>`).join('');};
  fill();
  property.addEventListener('change',fill);
}
function typeSelect(){return select('type_id','Charge category',state.types.map(t=>[t.id,t.name]));}
function unitName(u){return [u.property,u.owner,u.label].filter(x=>x&&String(x).trim()).join(' / ');}
function showForm(title,route,fields,defaults={},hint=''){
  const dialog=$('#modal');dialog.innerHTML=`<header><h2>${title}</h2><button class="close" data-action="close" aria-label="Close dialog">×</button></header>${hint?`<div class="hint">${hint}</div>`:''}<form id="record-form"><div class="form">${fields}</div><div class="error" id="form-error"></div><footer>${button('close','Cancel',false,'type="button"')}${button('none','Save',true,'type="submit"')}</footer></form>`;dialog.showModal();
  $('#record-form').addEventListener('submit',async e=>{e.preventDefault();const submit=e.target.querySelector('[type=submit]');submit.disabled=true;try{const result=await api(route,{...defaults,...Object.fromEntries(new FormData(e.target))});dialog.close();if(route==='password'){state=null;authScreen('signin');toast('Password updated. Sign in with your new password.');}else{await reload();toast(result.created!==undefined?`${result.created} new charge(s) generated.`:'Saved successfully.');}}catch(err){$('#form-error').textContent=err.message;}finally{submit.disabled=false;}});
}
function forms(action,id){
  const month=state.today.slice(0,7);
  if(action==='property')showForm('Add property','properties',field('name','Property name')+field('address','Address / location','text','',true));
  if(action==='unit')showForm('Add unit','units',select('property_id','Property',state.properties.map(p=>[p.id,p.name]))+field('owner','Owner name (optional)','text','',false,false)+field('label','Unit label'),{},'Choose the property, enter the owner’s name if known, and a unit label such as A01. Each unit label must be unique within its property.');
  if(action==='contact'||action==='contact-edit'){const c=action==='contact-edit'?state.contacts.find(c=>c.id===+id):{};const currentUnit=state.units.find(u=>u.id===c.unit_id);showForm(action==='contact-edit'?'Edit contact':'Register tenant or owner',action==='contact-edit'?'contact-edit':'contacts',propertySelect(currentUnit?currentUnit.property_id:'')+unitLabelField(currentUnit?currentUnit.label:'')+select('kind','Contact type',[['Tenant','Tenant'],['Owner','Owner']],true,c.kind)+field('name','Full name','text',c.name||'')+field('phone','Phone number (international)','tel',c.phone||'')+field('alternate_phone','Alternate phone number (optional)','tel',c.alternate_phone||'',false,false)+select('notify','Should receive reminders?',[['1','Yes'],['0','No']],true,c.notify??1)+field('billing_start','Start of billing period (exact date)','date',c.billing_start||'',true),c.id?{id:c.id}:{},'Choose the property, then type the unit — a unit that does not exist yet is created automatically and then appears in Charges, Reminders and Statements. Use + country code and digits for the phone. Alternate numbers are included only when manually selected in Reminders. Register a property first if none is listed.');bindUnitOptions();}
  if(action==='type')showForm('Add charge category','types',field('name','Category name','text','',true));
  if(action==='plan')showForm('Set monthly recurring fee','plans',unitSelect()+typeSelect()+field('amount','Monthly amount','number')+select('due_day','Due day',Array.from({length:31},(_,i)=>[i+1,i+1]),true,30)+field('start_period','First billing period','month',month)+field('end_period','Last period (optional)','month','',false,false),{},'Plans do not change existing charges. Generate a period to apply them now. Due days beyond a month’s length use its last day.');
  if(action==='charge')showForm('Add charge / historical arrears','charges',unitSelect()+typeSelect()+field('period','Original billing period','month',month)+field('due','Due date','date',state.today)+field('amount','Charge amount','number')+field('source','Reason / source','text','Manual charge'),{},'Enter original billed amounts and record their payments separately. Alternatively enter only the unpaid historical amount and describe it as opening arrears; do not also import the same original charge.');
  if(action==='generate')showForm('Generate monthly charges','generate',field('period','Billing period','month',month,true),{},'Uses active plans. Running the same period again never duplicates a unit/category charge.');
  if(action==='payment')showForm('Record received payment','payments',unitSelect()+field('amount','Received amount','number')+field('paid_on','Date received','date',state.today)+field('reference','Receipt / bank reference'),{request_key:crypto.randomUUID()},'Allocation is oldest due date first, across all categories for this unit. Excess remains as credit. Reuse the existing form after a connection error to avoid submitting a payment twice.');
  if(action==='reverse')showForm('Reverse payment','reverse',field('reason','Reason for reversal','text','',true),{id:+id},'This restores balances covered by the payment. The original record remains visible.');
  if(action==='staff')showForm('Add staff account','staff',field('name','Name')+field('email','Staff email','email')+select('role','Access role',[['admin','Administrator'],['billing','Billing officer'],['viewer','Read-only viewer']],true,'admin')+field('password','Initial password','password'),{},'Administrator has full access and can sign in at any time. Each password must be unique: an email or a password already used on another account is refused, for security. The staff member can change their password in Settings.');
  if(action==='password')showForm('Change my password','password',field('current_password','Current password','password','',true)+field('new_password','New password','password','',true));
  if(action==='settings'){const s=state.settings;showForm('Organization settings','settings',field('currency','Currency code','text',s.currency)+field('country','Country code','text',s.country)+field('utc_offset','UTC offset in minutes','text',s.utc_offset)+select('automatic','Automatic billing + reminders',[['0','Disabled'],['1','Enabled']],true,s.automatic)+select('lead_days','Days before due date',Array.from({length:31},(_,i)=>[i,i]),true,s.lead_days)+select('repeat_days','Repeat every N days after due date',Array.from({length:90},(_,i)=>[i+1,i+1]),true,s.repeat_days)+select('quiet_start','Quiet hours start',Array.from({length:24},(_,i)=>[i,`${i}:00`]),true,s.quiet_start)+select('quiet_end','Quiet hours end',Array.from({length:24},(_,i)=>[i,`${i}:00`]),true,s.quiet_end)+field('segment_price','Price per SMS segment (0 if unknown)','text',(s.segment_price/100).toFixed(2)),{},'UGX / Uganda / UTC+3 are initial examples. Set these before entering money. Currency locks after financial records are created. Fixed timezone offsets do not adjust for daylight saving.');}
}
async function previewSelected(){
  const ids=[...document.querySelectorAll('input[name=charge]:checked')].map(i=>+i.value);
  if(!ids.length)throw Error('Select at least one outstanding charge first.');
  preview=await api('preview',{charge_ids:ids,penalty:$('#penalty')?.value||'',include_alternate:$('#include-alternate')?.checked||false});
  const dialog=$('#modal');dialog.innerHTML=`<header><h2>${sendingLive()?'Review reminder before sending':'Review reminder (test mode)'}</h2><button class="close" data-action="close" aria-label="Close dialog">×</button></header><div class="hint warning">${sendingLive()?'Confirming sends a real SMS to every recipient listed below.':'Test mode: no SMS will be sent.'} Preview expires in 10 minutes. Notices communicate staff policy only; they perform no external action.</div><p><strong>${preview.items.length} recipient message(s)</strong> · Estimated provider cost: ${currency(preview.estimated_cost)} ${state.settings.segment_price===0?'(segment price not set)':''}</p><div class="preview-list">${preview.items.length?preview.items.map(i=>`<div class="preview-card"><strong>${esc(i.name)}</strong> · ${esc(i.phone)}<div class="small muted">${esc(i.recipient_type)} number · Unit ${esc(i.unit)} · ${esc(i.period)} · ${i.segments} estimated segment(s)${i.penalty?' · Manual penalty notice included':''}</div><p>${esc(i.body)}</p></div>`).join(''):empty('No eligible recipients','Add active contacts with notifications enabled to the selected units.')}</div><div class="error" id="preview-error"></div><footer>${button('close','Cancel')}${preview.items.length?button('confirm-send',sendingLive()?'Send reminders':'Confirm (test mode)',true):''}</footer>`;dialog.showModal();
}
document.addEventListener('click',async e=>{
  const nav=e.target.closest('[data-page]');if(nav){page=nav.dataset.page;render();return;}
  const target=e.target.closest('[data-action]');if(!target)return;const action=target.dataset.action,id=target.dataset.id;if(action==='none')return;
  try{
    if(action==='close'){$('#modal').close();return;}
    if(action==='reload'){await boot();return;}
    if(action==='auth-signin'){authScreen('signin');return;}
    if(action==='auth-signup'){authScreen('signup');return;}
    if(action==='logout'){await api('logout',{});state=null;authScreen('signin');return;}
    if(action==='guide'||action==='reminders'){page=action==='guide'?'User Guide':'Reminders';render();return;}
    if(action==='guided-demo'){page='Guided Demo';render();return;}
    if(action==='penalty-example'){$('#penalty').value="Your Pacific Victoria elevator access card may be deactivated under the property's policy if the overdue payment remains unpaid.";return;}
    if(action==='demo-pay'){demoPaid=20000000;demoResult=false;render();return;}
    if(action==='demo-simulate'){demoResult=true;render();return;}
    if(action==='demo-penalty'){demoPenalty=!demoPenalty;demoResult=false;render();return;}
    if(action==='demo-reset'){demoPaid=0;demoResult=false;demoPenalty=false;render();return;}
    if(action==='filter-c'){updateCharges();return;}
    if(action==='filter-r'){updateReminderSelection();return;}
    if(action==='refresh'){await reload();return;}
    if(action==='history-all'){openHistory(target.dataset.kind);return;}
    if(action==='st-view-sent'){viewSentStatement(id);return;}
    if(action==='close-statement-view'){target.closest('dialog')?.close();return;}
    if(action==='hs-7'){setHistoryRange(7);return;}
    if(action==='hs-30'){setHistoryRange(30);return;}
    if(action==='hs-90'){setHistoryRange(90);return;}
    if(action==='hs-365'){setHistoryRange(365);return;}
    if(action==='hs-all'){historyFilter.from='';historyFilter.to='';syncHistoryRange();renderHistory();return;}
    if(action==='hs-csv'){historyCSV();return;}
    if(action==='help'){openHelp(page);return;}
    if(action==='help-page'){openHelp(target.dataset.page);return;}
    if(action==='toggle-password'){document.querySelectorAll('input.pw').forEach(i=>i.type=target.checked?'text':'password');return;}
    if(action==='print-statement'){window.print();return;}
    if(action==='st-new'){statementDraft=blankStatement();statementDirty=false;statementSourceUnit=0;statementRecipientPhone='';render();return;}
    if(action==='st-add-row'){captureStatement();statementDraft.rows.push({label:'',cells:statementDraft.columns.map(()=>'')});statementDirty=true;render();return;}
    if(action==='st-add-col'){captureStatement();statementDraft.columns.push('Quarter '+(statementDraft.columns.length+1));statementDraft.rows.forEach(r=>r.cells.push(''));statementDirty=true;render();return;}
    if(action==='st-fill'){fillFromRecords();render();return;}
    if(action==='st-preview'){captureStatement();previewStatement();return;}
    if(action==='st-save'){target.disabled=true;try{captureStatement();const saved=await api('statement-save',{statement:statementDraft});statementDraft.id=saved.id;statementDraft.token=saved.token;statementDirty=false;await reload();toast('Statement saved.');}catch(err){toast(err.message);}finally{target.disabled=false;}return;}
    if(action==='st-send'){target.disabled=true;try{await sendStatement();}catch(err){toast(err.message);}finally{target.disabled=false;}return;}
    if(action==='select-all'){document.querySelectorAll('input[name=charge]').forEach(i=>i.checked=true);return;}
    if(action==='preview'){await previewSelected();return;}
    if(action==='confirm-send'){target.disabled=true;try{const result=await api('send',{token:preview.token});$('#modal').close();await reload();toast(sendingLive()?`${result.queued} message(s) queued for sending. Refresh after 15 seconds.`:`${result.queued} test message(s) queued (no SMS sent). Refresh after 15 seconds.`);}catch(err){$('#preview-error').textContent=err.message;}finally{target.disabled=false;}return;}
    if(action==='unit-toggle'){const u=state.units.find(u=>u.id===+id);await api('unit-status',{id:+id,active:u.active?0:1});await reload();return;}
    if(action==='contact-toggle'||action==='notify-toggle'){const c=state.contacts.find(c=>c.id===+id);await api('contact-status',{id:+id,active:action==='contact-toggle'?(c.active?0:1):c.active,notify:action==='notify-toggle'?(c.notify?0:1):c.notify});await reload();return;}
    if(action==='stop-plan'){showForm('Stop recurring plan','plan-status','<p class="full">Existing charges remain. No new charges will be generated from this plan.</p>',{id:+id});return;}
    if(action==='demo'){target.disabled=true;try{await api('demo',{});await reload();toast('Fictional demo records added. No messages sent.');}finally{target.disabled=false;}return;}
    if(action==='backup'){target.disabled=true;try{const result=await api('backup',{});toast('Backup verified and saved: '+result.file);}finally{target.disabled=false;}return;}
    if(action==='install'){if(installPrompt){await installPrompt.prompt();installPrompt=null;}else toast('In Microsoft Edge, open the menu → Apps → Install this site as an app.');return;}
    if(action==='update'){if(safeToRefresh())location.reload();else toast('Save your work or close the form before updating.');return;}
    forms(action,id);
  }catch(err){toast(err.message);}
});
window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();installPrompt=e;});
window.addEventListener('offline',()=>{$('#notice').textContent='Connection lost. Financial changes cannot be saved until the server is reachable.';});
window.addEventListener('online',()=>{$('#notice').textContent='';});
let swRegistration=null, updatePending=false;
function safeToRefresh(){if($('#modal')&&$('#modal').open)return false;if(document.querySelector('input:focus, textarea:focus, select:focus'))return false;if(page==='Statements'&&statementDirty)return false;return true;}
if('serviceWorker' in navigator){
  const hadController=!!navigator.serviceWorker.controller;
  navigator.serviceWorker.register('/sw.js').then(reg=>{
    swRegistration=reg;
    navigator.serviceWorker.addEventListener('controllerchange',()=>{
      if(!hadController||updatePending)return;
      updatePending=true;
      if(safeToRefresh())location.reload();
      else $('#notice').innerHTML='An update is ready. It will apply automatically once you finish editing.'+button('update','Apply now');
    });
  }).catch(()=>{});
}
boot();
