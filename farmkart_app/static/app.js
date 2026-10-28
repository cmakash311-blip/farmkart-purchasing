'use strict';
const state={user:null,csrf:'',branches:[],branch:'',view:'dashboard',farmers:[],lineCount:0,lastBill:null};
const $=s=>document.querySelector(s);
const money=v=>'₹'+Number(v||0).toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2});
const number=v=>Number(v||0).toLocaleString('en-IN',{maximumFractionDigits:3});
const text=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const choice=(val,label,selected=false)=>`<option value="${text(val)}" ${selected?'selected':''}>${text(label)}</option>`;
const token=()=>Array.from(crypto.getRandomValues(new Uint8Array(32)),b=>b.toString(16).padStart(2,'0')).join('');
const el=(tag,html,cls)=>`<${tag}${cls?' class="'+cls+'"':''}>${html}</${tag}>`;
const title=(label,desc,action='')=>`<div class="page-head"><div><div class="eyebrow">FARMKART FOODS / ${text(state.branches.find(b=>String(b.id)===state.branch)?.name||'ALL FACTORIES')}</div><h2>${label}</h2><p>${desc}</p></div>${action}</div>`;
function notify(message,kind='good'){const e=$('#notice');e.textContent=message;e.className='notice '+kind;e.hidden=false;clearTimeout(notify.t);notify.t=setTimeout(()=>e.hidden=true,6500)}
async function api(path,method='GET',body){let options={method,headers:{}};if(body!==undefined){options.headers['Content-Type']='application/json';options.body=JSON.stringify(body)}if(!['GET','HEAD'].includes(method))options.headers['X-CSRF-Token']=state.csrf;let r;try{r=await fetch('/api'+path,options)}catch{throw Error('Cannot reach the server. Check your internet connection. Do not submit the transaction repeatedly.')}let obj;try{obj=await r.json()}catch{throw Error('Invalid response from the server')}if(!r.ok){if(r.status===401){showLogin()}throw Error(typeof obj.detail==='string'?obj.detail:'Request failed')}return obj}
function showLogin(){state.user=null;$('#shell').hidden=true;$('#login').hidden=false;$('#password').value=''}
async function initialize(){try{const me=await api('/me');state.user=me;state.csrf=me.csrf_token;state.branches=await api('/branches');state.branch=me.role==='OWNER'?'':String(me.branch_id);$('#login').hidden=true;$('#shell').hidden=false;$('#user-name').textContent=me.name;$('#user-role').textContent=me.role;$('#users-nav').hidden=me.role!=='OWNER';$('#audit-nav').hidden=me.role!=='OWNER';const branchSelector=$('#branch-filter');branchSelector.innerHTML=(me.role==='OWNER'?choice('','All factories'): '')+state.branches.map(b=>choice(b.id,b.name)).join('');branchSelector.value=state.branch;branchSelector.disabled=me.role!=='OWNER';navigate('dashboard')}catch(e){showLogin()}}
$('#login-form').addEventListener('submit',async e=>{e.preventDefault();const btn=e.target.querySelector('button');btn.disabled=true;$('#login-error').hidden=true;try{const data=await api('/login','POST',{username:$('#username').value,password:$('#password').value});state.csrf=data.csrf_token;await initialize()}catch(err){$('#login-error').textContent=err.message;$('#login-error').hidden=false}finally{btn.disabled=false}});
$('#logout').onclick=async()=>{try{await api('/logout','POST',{})}finally{showLogin()}};
$('#branch-filter').onchange=e=>{state.branch=e.target.value;navigate(state.view)};
$('#mobile-menu').onclick=()=>$('#sidebar').classList.toggle('open');
$$('#navigation .nav').forEach(btn=>btn.onclick=()=>navigate(btn.dataset.view));
function $$(s){return Array.from(document.querySelectorAll(s))}
function navigate(view){state.view=view;$('#sidebar').classList.remove('open');$$('#navigation .nav').forEach(b=>b.classList.toggle('active',b.dataset.view===view));const names={dashboard:'Overview',new:'New purchase bill',purchases:'Purchase register',farmers:'Farmers',payments:'Cheques & payments',reports:'Reports & exports',users:'Staff & user management',audit:'Audit history'};$('#top-title').textContent=names[view];$('#view').innerHTML='<div class="panel"><div class="empty">Loading…</div></div>';const f=({dashboard:renderDashboard,new:renderNew,purchases:renderPurchases,farmers:renderFarmers,payments:renderPayments,reports:renderReports,users:renderUsers,audit:renderAudit})[view];f().catch(err=>{$('#view').innerHTML=`<div class="notice bad">${text(err.message)}</div>`})}
function scope(){return state.branch?'?branch_id='+encodeURIComponent(state.branch):''}
function table(headers,rows,empty='No records found'){return `<div class="table-wrap"><table><thead><tr>${headers.map(h=>`<th>${text(h)}</th>`).join('')}</tr></thead><tbody>${rows.length?rows.join(''):`<tr><td class="empty" colspan="${headers.length}"><strong>${text(empty)}</strong>New records will appear here.</td></tr>`}</tbody></table></div>`}
async function renderDashboard(){let [d,all]=await Promise.all([api('/dashboard'+scope()),api('/purchases'+scope())]);$('#view').innerHTML=title('Purchasing overview','Live purchasing visibility across your authorized factories.',`<button class="primary" id="quick-new">+ New purchase</button>`)+`<div class="grid four"><div class="stat"><div class="kicker">Today’s purchases <span class="emoji">▤</span></div><div class="number">${d.today_bills}</div><div class="foot">Bills posted today</div></div><div class="stat"><div class="kicker">Today’s quantity <span class="emoji">♧</span></div><div class="number">${number(d.today_kg)} <small>kg</small></div><div class="foot">Net peanut weight</div></div><div class="stat"><div class="kicker">Today’s purchase value <span class="emoji">₹</span></div><div class="number">${money(d.today_value)}</div><div class="foot">After charges and adjustments</div></div><div class="stat"><div class="kicker">Outstanding payments <span class="emoji">◷</span></div><div class="number">${money(d.outstanding)}</div><div class="foot">Includes pending cheques / bank transfers</div></div></div><div class="grid two" style="margin-top:21px"><div class="panel"><h3>All-time purchasing</h3><div class="detail-grid"><div><small>Total bills</small><strong>${d.all_bills}</strong></div><div><small>Total net weight</small><strong>${number(d.all_kg)} kg</strong></div><div><small>Total payable</small><strong>${money(d.total_purchase_value)}</strong></div></div></div><div class="panel"><h3>Payment instruments</h3><div class="stat" style="border:0;box-shadow:none;padding:0"><div class="kicker">Cheque / bank transfer pending clearance</div><div class="number">${money(d.pending_instruments)}</div></div></div></div><div class="panel" style="margin-top:20px"><div class="row" style="justify-content:space-between"><h3>Recent purchase bills</h3><button class="secondary" id="all-purchases">View all →</button></div>${table(['Bill','Factory','Farmer','Date','Net kg','Payable'],all.slice(0,8).map(p=>`<tr><td><button class="link" data-bill="${p.id}">${text(p.number)}</button></td><td>${text(p.branch)}</td><td>${text(p.farmer)}</td><td>${text(p.date)}</td><td>${number(p.net_kg)}</td><td>${money(p.payable)}</td></tr>`),'No purchase bills yet')}</div>`;$('#quick-new').onclick=()=>navigate('new');$('#all-purchases').onclick=()=>navigate('purchases');wireBills()}
async function renderFarmers(){
  const canCreate=['OWNER','PURCHASE'].includes(state.user.role);
  $('#view').innerHTML=title('Farmer directory','One farmer directory shared between Himatnagar and Modasa.',canCreate?'<button class="primary" id="add-farmer">+ Register farmer</button>':'')+`<div class="panel"><div class="filters"><input id="farmer-search" placeholder="Search farmer / village / mobile"></div><p class="help">Showing up to 100 matching farmers. Search by name, village or mobile to find older records.</p><div id="farmers-table"></div></div>`;
  let current=0,timer;
  async function lookup(){let serial=++current;const q=$('#farmer-search').value.trim();const rows=await api('/farmers?limit=100&search='+encodeURIComponent(q));if(serial!==current)return;
    $('#farmers-table').innerHTML=table(['Farmer ID','Farmer name','Village','Mobile','Cooperative'],rows.map(f=>`<tr><td>${text(f.code)}</td><td><strong>${text(f.name)}</strong></td><td>${text(f.village)}</td><td>${text(f.mobile||'—')}</td><td>${text(f.cooperative||'—')}</td></tr>`),'No matching farmers')}
  $('#farmer-search').oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>lookup().catch(e=>notify(e.message,'bad')),250)};
  if($('#add-farmer'))$('#add-farmer').onclick=farmerModal;
  await lookup();
}
function openModal(html){$('#modal-content').innerHTML=html;$('#modal').hidden=false}
function closeModal(){$('#modal').hidden=true;$('#modal-content').innerHTML=''}
$('#modal-close').onclick=closeModal;$('#modal').addEventListener('click',e=>{if(e.target.id==='modal')closeModal()});
function farmerModal(done){openModal(`<h2>Register farmer</h2><p class="muted">This profile can be used at either factory.</p><form id="farmer-form" class="grid"><div class="form-grid two"><label>Farmer full name *<input name="name" required minlength="2" maxlength="140"></label><label>Village *<input name="village" required minlength="2" maxlength="140"></label><label>Mobile<input name="mobile" maxlength="20" inputmode="tel"></label><label>Cooperative (optional)<input name="cooperative" maxlength="140"></label></div><div id="farmer-modal-error" class="error-text"></div><button class="primary">Save farmer</button></form>`);$('#farmer-form').onsubmit=async e=>{e.preventDefault();const b=e.target.querySelector('button');b.disabled=true;try{const fd=Object.fromEntries(new FormData(e.target));const farmer=await api('/farmers','POST',fd);closeModal();notify('Farmer registered successfully.');if(typeof done==='function')await done(farmer);else navigate('farmers')}catch(err){$('#farmer-modal-error').textContent=err.message}finally{b.disabled=false}}}
async function renderPurchases(){const bills=await api('/purchases'+scope());$('#view').innerHTML=title('Purchase register','Every posted bill has its own permanent factory-specific number.','<button id="new-from-reg" class="primary">+ New purchase</button>')+`<div class="panel"><div class="filters"><input id="bill-search" placeholder="Search bill / farmer / village / RST"><select id="bill-factory"><option value="">All visible factories</option>${state.branches.map(b=>choice(b.id,b.name)).join('')}</select></div><div id="purchase-table"></div></div>`;$('#bill-factory').value=state.branch;function display(){const q=$('#bill-search').value.toLowerCase().trim(),b=$('#bill-factory').value;let rows=bills.filter(p=>(!b||String(p.branch_id)===b)&&[p.number,p.farmer,p.village,p.rst].some(x=>String(x).toLowerCase().includes(q)));$('#purchase-table').innerHTML=table(['Bill','Date','Factory','Farmer','Net kg','Payable','Outstanding',''],rows.map(p=>`<tr><td><button class="link" data-bill="${p.id}">${text(p.number)}</button></td><td>${text(p.date)}</td><td>${text(p.branch)}</td><td><strong>${text(p.farmer)}</strong><br><small>${text(p.village)}</small></td><td>${number(p.net_kg)}</td><td>${money(p.payable)}</td><td>${money(p.payments_summary.outstanding)}</td><td><button class="secondary" data-bill="${p.id}">Open</button></td></tr>`));wireBills()}$('#new-from-reg').onclick=()=>navigate('new');$('#bill-search').oninput=display;$('#bill-factory').onchange=display;display()}
function wireBills(){$$('[data-bill]').forEach(b=>b.onclick=()=>billModal(+b.dataset.bill).catch(e=>notify(e.message,'bad')))}
let savedSubmission=null;
async function renderNew(){if(!['OWNER','PURCHASE'].includes(state.user.role)){$('#view').innerHTML='<div class="notice bad">You do not have permission to create purchase bills.</div>';return}const farmers=await api('/farmers?limit=60');state.farmers=farmers;state.lineCount=0;savedSubmission=token();$('#view').innerHTML=title('New purchase bill','Enter farmer details, peanut weights, purchase rate and deductions.')+`<form id="purchase-form" class="purchase-layout"><div class="grid"><div class="panel"><div class="panel-subtitle">01 / Farmer & arrival</div><div class="form-grid two"><label>Factory *<select id="purchase-branch" required>${state.branches.map(b=>choice(b.id,b.name,String(b.id)===state.branch)).join('')}</select></label><label>Search farmer (name / mobile / village)<input id="farmer-lookup" placeholder="Type to search all farmers"></label><label>Farmer *<select id="purchase-farmer" required>${choice('','Select registered farmer')}${farmers.map(f=>choice(f.id,`${f.name} · ${f.village} · ${f.code}`)).join('')}</select></label><label>RST / Pavati no.<input id="rst" maxlength="80" placeholder="Arrival reference"></label><label>Vehicle number<input id="vehicle" maxlength="60" placeholder="GJ-…"></label></div><button id="new-farmer" type="button" class="secondary" style="margin-top:15px">+ Register new farmer</button></div><div class="panel"><div class="panel-subtitle">02 / Peanut purchase line items</div><div id="purchase-lines"></div><button type="button" class="secondary" id="add-line">+ Add peanut variety / lot</button><p class="help">Rates are in ₹ per 20 kg. Amount = net kg × rate ÷ 20.</p></div><div class="panel"><div class="panel-subtitle">03 / Charges, adjustments & notes</div><div class="form-grid two"><label>Weighbridge charges (₹)<input id="charges" type="number" value="0" min="0" step="0.01"></label><label>Other deductions (₹)<input id="deductions" type="number" value="0" min="0" step="0.01"></label><label>Round adjustment (₹)<input id="adjust" type="number" value="0" step="0.01"></label><label>Notes / quality remarks<textarea id="notes" rows="2" maxlength="1000"></textarea></label></div></div></div><div class="panel" style="position:sticky;top:15px"><div class="panel-subtitle">Live bill preview</div><div class="right-note">Final amounts will be recomputed and assigned a permanent bill number by the server.</div><div class="amount-box"><div class="amount-line"><span>Gross kg</span><strong id="v-gross">0</strong></div><div class="amount-line"><span>Kapat kg</span><strong id="v-kapat">0</strong></div><div class="amount-line"><span>Net kg</span><strong id="v-net">0</strong></div><div class="amount-line"><span>Purchase value</span><strong id="v-value">₹0.00</strong></div><div class="amount-line"><span>Charges & deductions</span><strong id="v-deduct">₹0.00</strong></div><div class="amount-line final"><span>Farmer payable</span><span id="v-final">₹0.00</span></div></div><div id="bill-error" class="error-text"></div><button type="submit" class="primary full" id="post-bill" style="margin-top:16px">Post final purchase bill →</button><p class="right-note" style="margin-top:12px">Once posted, bills cannot be edited in this pilot. Verify all amounts before posting.</p></div></form>`;if(state.branch)$('#purchase-branch').value=state.branch;$('#new-farmer').onclick=()=>farmerModal(async f=>{state.farmers.push(f);const s=$('#purchase-farmer');s.add(new Option(`${f.name} · ${f.village} · ${f.code}`,f.id));s.value=f.id});$('#add-line').onclick=()=>addLine();addLine();
  let searchSerial=0,timer;
  $('#farmer-lookup').oninput=()=>{clearTimeout(timer);timer=setTimeout(async()=>{
    const serial=++searchSerial,query=$('#farmer-lookup').value.trim();
    try{const results=await api('/farmers?limit=60&search='+encodeURIComponent(query));if(serial!==searchSerial)return;
      const select=$('#purchase-farmer');select.innerHTML=choice('','Select registered farmer')+results.map(f=>choice(f.id,`${f.name} · ${f.village} · ${f.code}`)).join('');
      if(results.length===1)select.value=String(results[0].id);
    }catch(e){notify(e.message,'bad')}
  },240)};
  $('#purchase-form').oninput=calculate;$('#purchase-form').onsubmit=submitBill}
function addLine(){if(state.lineCount>=25){notify('Maximum 25 items per bill.','bad');return}const idx=state.lineCount++;const e=document.createElement('div');e.className='item-grid';e.innerHTML=`<label>Variety<input class="line-variety" value="Java" maxlength="80" required list="varieties"><datalist id="varieties"><option value="Java"><option value="Bold"><option value="TJ"><option value="In-shell"><option value="Other"></datalist></label><label>Gross kg<input class="line-gross" type="number" min="0.001" max="10000000" step="0.001" required placeholder="1000"></label><label>Kapat kg<input class="line-kapat" type="number" min="0" max="10000000" step="0.001" value="0" required></label><label>Rate / 20kg (₹)<input class="line-rate" type="number" min="0.01" max="10000000" step="0.01" required placeholder="2200"></label><button type="button" class="mini-button" title="Remove line">×</button>`;e.querySelector('button').onclick=()=>{e.remove();calculate()};$('#purchase-lines').append(e);calculate()}
function lines(){return $$('#purchase-lines .item-grid').map(r=>({variety:r.querySelector('.line-variety').value.trim(),gross_kg:r.querySelector('.line-gross').value,kapat_kg:r.querySelector('.line-kapat').value||'0',rate_per_20kg:r.querySelector('.line-rate').value}))}
function calculate(){const all=lines(),n=v=>Number(v||0);let gross=0,kapat=0,val=0;for(const x of all){gross+=n(x.gross_kg);kapat+=n(x.kapat_kg);val+=Math.round(Math.max(0,n(x.gross_kg)-n(x.kapat_kg))*n(x.rate_per_20kg)/20*100)/100}const deduct=n($('#charges').value)+n($('#deductions').value),end=val-deduct+n($('#adjust').value);$('#v-gross').textContent=number(gross);$('#v-kapat').textContent=number(kapat);$('#v-net').textContent=number(gross-kapat);$('#v-value').textContent=money(val);$('#v-deduct').textContent=money(deduct);$('#v-final').textContent=money(end)}
async function submitBill(e){e.preventDefault();const err=$('#bill-error');err.textContent='';const all=lines();if(!all.length){err.textContent='Add at least one peanut purchase line.';return}if(all.some(x=>+x.kapat_kg>=+x.gross_kg)){err.textContent='Kapat must be less than gross weight.';return}if(!$('#purchase-farmer').value){err.textContent='Select a farmer.';return}if(!confirm('Post this purchase bill permanently? Verify weight, rate and farmer before continuing.'))return;const body={idem_key:savedSubmission,branch_id:Number($('#purchase-branch').value),farmer_id:Number($('#purchase-farmer').value),rst_number:$('#rst').value,vehicle_number:$('#vehicle').value,weighbridge_charges:$('#charges').value,other_deductions:$('#deductions').value,round_adjustment:$('#adjust').value,notes:$('#notes').value,lines:all};const btn=$('#post-bill');btn.disabled=true;btn.textContent='Posting bill…';try{const result=await api('/purchases','POST',body);notify(`Purchase bill ${result.purchase.number} saved.`);await billModal(result.purchase.id);savedSubmission=token();navigate('purchases')}catch(ex){err.textContent=ex.message+' If the connection failed, check the purchase register before retrying.'}finally{btn.disabled=false;btn.textContent='Post final purchase bill →'}}
async function billModal(id){const p=await api('/purchases/'+id);const lines=p.lines.map(x=>`<tr><td>${text(x.variety)}</td><td>${number(x.gross_kg)}</td><td>${number(x.kapat_kg)}</td><td>${number(x.net_kg)}</td><td>${money(x.rate_per_20kg)}</td><td>${money(x.amount)}</td></tr>`).join('');const pays=p.payments.map(pay=>`<tr><td>${text(pay.method)}</td><td>${money(pay.amount)}</td><td>${text(pay.reference||'—')}</td><td>${text(pay.status)}</td></tr>`).join('');openModal(`<div class="no-print"><div class="row" style="justify-content:space-between;padding-right:24px;margin-bottom:18px"><h3>Purchase bill ${text(p.number)}</h3><button class="primary" id="print-bill">Print receipt</button></div></div><div class="receipt"><div class="receipt-header"><h2>Farmkart Foods</h2><p>PEANUT PURCHASE RECEIPT · ${text(p.branch)}</p><p>કૃષિ ઉત્પાદન ખરીદી રસીદ</p></div><div class="receipt-grid"><div>Bill no.: <strong>${text(p.number)}</strong></div><div>Date: <strong>${text(p.date)}</strong></div><div>Farmer: <strong>${text(p.farmer)}</strong></div><div>Village: <strong>${text(p.village)}</strong></div><div>Mobile: <strong>${text(p.mobile||'—')}</strong></div><div>RST / Pavati: <strong>${text(p.rst||'—')}</strong></div><div>Vehicle: <strong>${text(p.vehicle||'—')}</strong></div><div>Factory: <strong>${text(p.branch)}</strong></div></div><table><thead><tr><th>Peanut variety</th><th>Gross kg</th><th>Kapat kg</th><th>Net kg</th><th>₹ / 20kg</th><th>Amount</th></tr></thead><tbody>${lines}</tbody></table><div style="max-width:320px;margin-left:auto;margin-top:18px"><div class="amount-line"><span>Gross purchase</span><strong>${money(p.gross_value)}</strong></div><div class="amount-line"><span>Weighbridge</span><strong>− ${money(p.weighbridge_charges)}</strong></div><div class="amount-line"><span>Other deduction</span><strong>− ${money(p.other_deductions)}</strong></div><div class="amount-line"><span>Round adjustment</span><strong>${money(p.round_adjustment)}</strong></div><div class="amount-line final"><span>Farmer payable</span><strong>${money(p.payable)}</strong></div></div><div class="receipt-foot"><small>Farmer signature</small><small>Authorized Farmkart signatory</small></div><p class="help" style="text-align:center">Computer-generated pilot receipt. Verify statutory document requirements before production.</p></div><div class="no-print"><div class="divider"></div><h3>Payment status</h3><div class="detail-grid"><div><small>Cleared</small><strong>${money(p.payments_summary.cleared)}</strong></div><div><small>Pending</small><strong>${money(p.payments_summary.pending)}</strong></div><div><small>Outstanding</small><strong>${money(p.payments_summary.outstanding)}</strong></div></div>${table(['Method','Amount','Reference','Status'],pays? p.payments.map(pay=>`<tr><td>${text(pay.method)}</td><td>${money(pay.amount)}</td><td>${text(pay.reference||'—')}</td><td>${text(pay.status)}</td></tr>`):[],'No payment entries')}${['OWNER','ACCOUNTS'].includes(state.user.role)&&Number(p.payments_summary.unallocated)>0?`<button id="record-payment" class="primary" style="margin-top:17px">+ Record payment</button>`:''}</div>`);$('#print-bill').onclick=()=>window.print();if($('#record-payment'))$('#record-payment').onclick=()=>paymentModal(p)}
function paymentModal(bill){openModal(`<h2>Record farmer payment</h2><p class="muted">Bill <strong>${text(bill.number)}</strong> · ${text(bill.farmer)}</p><div class="callout">Unallocated payable: <strong>${money(bill.payments_summary.unallocated)}</strong>. A cheque or bank transfer will remain pending until cleared.</div><form id="payment-form"><div class="form-grid two" style="margin-top:20px"><label>Payment method<select name="method" id="pay-method">${choice('CASH','Cash')}${choice('CHEQUE','Cheque')}${choice('BANK','Bank transfer')}</select></label><label>Amount ₹<input name="amount" value="${text(bill.payments_summary.unallocated)}" type="number" min="0.01" step="0.01" max="${text(bill.payments_summary.unallocated)}" required></label><label>Cheque / bank reference<input name="reference" maxlength="100" placeholder="Cheque number or UTR"></label><label>Instrument date<input name="instrument_date" type="date"></label></div><p id="payment-error" class="error-text"></p><button class="primary" style="margin-top:15px">Record payment</button></form>`);$('#payment-form').onsubmit=async e=>{e.preventDefault();const body=Object.fromEntries(new FormData(e.target));body.idem_key=paymentToken;body.instrument_date=body.instrument_date||null;try{await api('/purchases/'+bill.id+'/payments','POST',body);notify('Payment recorded.');await billModal(bill.id)}catch(ex){$('#payment-error').textContent=ex.message}};const paymentToken=token()}
async function renderPayments(){const payments=await api('/payments'+scope());$('#view').innerHTML=title('Cheques & payments','Review issued cheques, bank transfers, cash and clearance status.')+`<div class="panel"><div class="filters"><select id="pay-filter"><option value="">All payments</option><option value="PENDING">Pending clearance</option><option value="CLEARED">Cleared</option><option value="BOUNCED">Bounced</option></select></div><div id="payment-table"></div><p class="help">Only accounts and owner roles can record or finalize payments. Cash is cleared at entry; cheques and bank transfers need confirmation.</p></div>`;function display(){const f=$('#pay-filter').value,pp=payments.filter(p=>!f||p.status===f);$('#payment-table').innerHTML=table(['Bill','Farmer','Method','Reference','Amount','Status','Action'],pp.map(p=>`<tr><td><button class="link" data-bill="${p.purchase_id}">${text(p.bill_number)}</button></td><td>${text(p.farmer)}</td><td>${text(p.method)}</td><td>${text(p.reference||'—')}</td><td>${money(p.amount)}</td><td><span class="pill ${text(p.status.toLowerCase())}">${text(p.status)}</span></td><td>${p.status==='PENDING'&&['OWNER','ACCOUNTS'].includes(state.user.role)?`<button class="secondary" data-clear="${p.id}">Set status</button>`:'—'}</td></tr>`),'No payments yet');wireBills();$$('[data-clear]').forEach(b=>b.onclick=()=>statusModal(+b.dataset.clear))}$('#pay-filter').onchange=display;display()}
function statusModal(id){openModal(`<h2>Update payment status</h2><p class="muted">Mark this cheque or bank transfer only after checking bank evidence.</p><div class="grid"><button id="mark-cleared" class="primary">Mark cleared</button><button id="mark-bounced" class="secondary">Mark bounced / failed</button></div><p id="status-error" class="error-text"></p>`);for(const [selector,status] of [['#mark-cleared','CLEARED'],['#mark-bounced','BOUNCED']])$(selector).onclick=async()=>{if(!confirm('Confirm that the instrument status is '+status+'?'))return;try{await api('/payments/'+id+'/status','POST',{status});closeModal();notify('Payment status updated.');navigate('payments')}catch(e){$('#status-error').textContent=e.message}}}
async function renderUsers(){
  if(state.user.role!=='OWNER')throw Error('Owner access required');
  const [users,branches]=await Promise.all([api('/users'),state.branches.length?Promise.resolve(state.branches):api('/branches')]);
  $('#view').innerHTML=title('Staff & user management','Manage factory staff access, roles and login credentials across Himatnagar & Modasa.','<button id="add-user-btn" class="primary">+ Add staff member</button>')+
    `<div class="panel">
      <div class="filters">
        <input id="user-search" placeholder="Search staff by name or username">
      </div>
      <div id="users-table"></div>
      <p class="help">Owners have access to all factories and administrative settings. Purchasing and Accounts staff are strictly isolated to their assigned factory.</p>
    </div>`;
  function display(){
    const q=($('#user-search').value||'').toLowerCase().trim();
    const filtered=users.filter(u=>!q||u.name.toLowerCase().includes(q)||u.username.toLowerCase().includes(q)||u.role.toLowerCase().includes(q));
    $('#users-table').innerHTML=table(
      ['Staff name','Username','Role','Assigned factory','Status','Actions'],
      filtered.map(u=>{
        const isSelf=u.id===state.user.id;
        const rolePill=`<span class="pill ${u.role==='OWNER'?'cleared':u.role==='PURCHASE'?'pending':'bounced'}">${text(u.role)}</span>`;
        const statusPill=u.active
          ? `<span class="pill cleared">Active</span>`
          : `<span class="pill bounced">Disabled</span>`;
        const actions=[
          `<button class="secondary" data-reset-user="${u.id}" data-username="${text(u.username)}">Reset password</button>`
        ];
        if(!isSelf){
          actions.push(
            u.active
              ? `<button class="outline-btn" style="color:var(--bad, #dc2626)" data-toggle-user="${u.id}" data-active="0" data-username="${text(u.username)}">Deactivate</button>`
              : `<button class="secondary" data-toggle-user="${u.id}" data-active="1" data-username="${text(u.username)}">Activate</button>`
          );
        }
        return `<tr>
          <td><strong>${text(u.name)}</strong>${isSelf?' <small>(You)</small>':''}</td>
          <td><code>${text(u.username)}</code></td>
          <td>${rolePill}</td>
          <td>${text(u.branch_name)}</td>
          <td>${statusPill}</td>
          <td><div class="row" style="gap:6px">${actions.join('')}</div></td>
        </tr>`;
      }),
      'No staff members found'
    );
    $$('[data-reset-user]').forEach(btn=>{
      btn.onclick=()=>resetPasswordModal(+btn.dataset.resetUser,btn.dataset.username);
    });
    $$('[data-toggle-user]').forEach(btn=>{
      btn.onclick=()=>toggleUserStatus(+btn.dataset.toggleUser,btn.dataset.active==='1',btn.dataset.username);
    });
  }
  $('#user-search').oninput=display;
  $('#add-user-btn').onclick=()=>addUserModal(branches,async()=>renderUsers());
  display();
}

function genRandomPassword(){
  const chars='abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%';
  return 'Farm!'+Array.from(crypto.getRandomValues(new Uint8Array(10)),b=>chars[b%chars.length]).join('')+'#28';
}

function addUserModal(branches,done){
  const defaultPwd=genRandomPassword();
  openModal(`<h2>Add new staff member</h2>
    <p class="muted">Create login credentials for factory purchasing or accounts personnel.</p>
    <form id="new-user-form">
      <div class="form-grid two">
        <label>Full name *<input name="name" required minlength="2" maxlength="120" placeholder="e.g. Rajeshbhai Patel"></label>
        <label>Staff username *<input name="username" required minlength="3" maxlength="50" placeholder="e.g. rajesh_hmt" pattern="[a-zA-Z0-9_.-]+"></label>
        <label>System role *
          <select name="role" id="user-role-select" required>
            <option value="PURCHASE">PURCHASE (Weighbridge & Bills)</option>
            <option value="ACCOUNTS">ACCOUNTS (Payments & Cheques)</option>
            <option value="VIEWER">VIEWER (Read-only reports)</option>
            <option value="OWNER">OWNER (Full administrative access)</option>
          </select>
        </label>
        <label id="user-branch-wrap">Assigned factory *
          <select name="branch_id" id="user-branch-select" required>
            ${choice('','Select factory location')}
            ${branches.map(b=>choice(b.id,`${b.name} (${b.code})`)).join('')}
          </select>
        </label>
        <div style="grid-column: 1 / -1">
          <label>Initial password (min 12 characters) *
            <div class="row" style="gap:8px">
              <input name="password" id="user-password-input" value="${text(defaultPwd)}" required minlength="12" style="font-family:monospace">
              <button type="button" class="secondary" id="regen-pwd-btn">🎲 Generate</button>
            </div>
          </label>
          <small class="help">Save or share this password securely with the staff member.</small>
        </div>
      </div>
      <p id="user-modal-error" class="error-text"></p>
      <button class="primary" style="margin-top:15px">Create staff account</button>
    </form>`);
  const roleSelect=$('#user-role-select');
  const branchWrap=$('#user-branch-wrap');
  const branchSelect=$('#user-branch-select');
  roleSelect.onchange=()=>{
    if(roleSelect.value==='OWNER'){
      branchWrap.style.opacity='0.5';
      branchSelect.required=false;
      branchSelect.value='';
      branchSelect.disabled=true;
    }else{
      branchWrap.style.opacity='1';
      branchSelect.required=true;
      branchSelect.disabled=false;
    }
  };
  $('#regen-pwd-btn').onclick=()=>{
    $('#user-password-input').value=genRandomPassword();
  };
  $('#new-user-form').onsubmit=async e=>{
    e.preventDefault();
    const btn=e.target.querySelector('button.primary');
    btn.disabled=true;
    $('#user-modal-error').textContent='';
    try{
      const fd=Object.fromEntries(new FormData(e.target));
      if(fd.role==='OWNER')delete fd.branch_id;
      else fd.branch_id=Number(fd.branch_id);
      const created=await api('/users','POST',fd);
      closeModal();
      notify(`Staff account for ${created.name} (${created.username}) created.`);
      if(typeof done==='function')await done();
    }catch(err){
      $('#user-modal-error').textContent=err.message;
    }finally{
      btn.disabled=false;
    }
  };
}

function resetPasswordModal(userId,username){
  const defaultPwd=genRandomPassword();
  openModal(`<h2>Reset password</h2>
    <p class="muted">Set a new password for staff user <strong>${text(username)}</strong>.</p>
    <div class="callout">Existing active sessions for this staff member will be signed out immediately.</div>
    <form id="reset-pwd-form" style="margin-top:16px">
      <label>New password (min 12 characters) *
        <div class="row" style="gap:8px">
          <input name="new_password" id="reset-pwd-input" value="${text(defaultPwd)}" required minlength="12" style="font-family:monospace">
          <button type="button" class="secondary" id="regen-reset-btn">🎲 Generate</button>
        </div>
      </label>
      <p id="reset-modal-error" class="error-text"></p>
      <button class="primary" style="margin-top:16px">Update password</button>
    </form>`);
  $('#regen-reset-btn').onclick=()=>{
    $('#reset-pwd-input').value=genRandomPassword();
  };
  $('#reset-pwd-form').onsubmit=async e=>{
    e.preventDefault();
    const btn=e.target.querySelector('button.primary');
    btn.disabled=true;
    $('#reset-modal-error').textContent='';
    try{
      const fd=Object.fromEntries(new FormData(e.target));
      await api(`/users/${userId}/reset-password`,'POST',fd);
      closeModal();
      notify(`Password for ${username} updated successfully.`);
    }catch(err){
      $('#reset-modal-error').textContent=err.message;
    }finally{
      btn.disabled=false;
    }
  };
}

async function toggleUserStatus(userId,activate,username){
  const msg=activate
    ? `Activate staff account for ${username}? They will be able to log in again.`
    : `Deactivate staff account for ${username}? They will be immediately signed out and locked out.`;
  if(!confirm(msg))return;
  try{
    await api(`/users/${userId}/status`,'PATCH',{active:activate});
    notify(`User ${username} ${activate?'activated':'deactivated'}.`);
    navigate('users');
  }catch(e){
    notify(e.message,'bad');
  }
}

async function renderAudit(){if(state.user.role!=='OWNER')throw Error('Owner access required');let a=await api('/audit');$('#view').innerHTML=title('Audit history','Recorded actions by staff members for purchase and payment changes.')+`<div class="panel">${table(['Time (UTC)','User ID','Factory ID','Action','Entity','Details'],a.map(x=>`<tr><td>${text(x.at)}</td><td>${text(x.user_id)}</td><td>${text(x.branch_id||'—')}</td><td>${text(x.action)}</td><td>${text(x.entity)} #${text(x.entity_id)}</td><td>${text(x.details)}</td></tr>`))}</div>`}
initialize();
