'use strict';
const state={user:null,token:sessionStorage.getItem('fkf_token')||localStorage.getItem('fkf_token')||'',csrf:'',branches:[],branch:'',view:'dashboard',farmers:[],lineCount:0,lastBill:null,lang:localStorage.getItem('fkf_lang')||'gu'};
const $=s=>document.querySelector(s);
const money=v=>'₹'+Number(v||0).toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2});
const number=v=>Number(v||0).toLocaleString('en-IN',{maximumFractionDigits:3});
const text=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const choice=(val,label,selected=false)=>`<option value="${text(val)}" ${selected?'selected':''}>${text(label)}</option>`;
const token=()=>Array.from(crypto.getRandomValues(new Uint8Array(32)),b=>b.toString(16).padStart(2,'0')).join('');
const el=(tag,html,cls)=>`<${tag}${cls?' class="'+cls+'"':''}>${html}</${tag}>`;
const title=(label,desc,action='')=>`<div class="page-head"><div><div class="eyebrow">FARMKART FOODS / ${text(state.branches.find(b=>String(b.id)===state.branch)?.name||'ALL FACTORIES')}</div><h2>${label}</h2><p>${desc}</p></div>${action}</div>`;

const I18N={
  en:{
    lang_btn:'English',dashboard:'Overview',new:'New purchase bill',purchases:'Purchase register',
    farmers:'Farmers & Khata',payments:'Cheques & payments',reports:'Reports & exports',
    users:'Staff & user management',audit:'Audit history',factory:'Factory',farmer:'Farmer',
    village:'Village',mobile:'Mobile',variety:'Variety',bags:'Bags (કટ્ટા)',tare:'Tare/bag (kg)',
    gross_kg:'Gross kg',kapat_kg:'Kapat kg',net_kg:'Net kg',rate_20kg:'Rate / 20kg (₹)',
    purchase_val:'Purchase value',farmer_payable:'Farmer payable',charges:'Weighbridge charges (₹)',
    deductions:'Other deductions (₹)',adjust:'Round adjustment (₹)',post_bill:'Post final purchase bill →'
  },
  gu:{
    lang_btn:'ગુજરાતી',dashboard:'ડેશબોર્ડ (ઓવરવ્યૂ)',new:'નવી ખરીદી પાવતી',purchases:'ખરીદી રજીસ્ટર',
    farmers:'ખેડૂત યાદી અને ખાતાવહી',payments:'ચૂકવણી અને ચેક',reports:'અહેવાલ અને નિકાસ',
    users:'કર્મચારી વ્યવસ્થાપન',audit:'ઓડિટ હિસ્ટ્રી',factory:'ફેક્ટરી',farmer:'ખેડૂત',
    village:'ગામ',mobile:'મોબાઈલ',variety:'મગફળી જાત',bags:'કટ્ટા (બોરી)',tare:'બારદાન વજન (કિલો)',
    gross_kg:'કુલ વજન (કિલો)',kapat_kg:'કપાત (કિલો)',net_kg:'ચોખ્ખું વજન (કિલો)',rate_20kg:'ભાવ / મણ (૨૦ કિલો)',
    purchase_val:'ખરીદી રકમ',farmer_payable:'ચૂકવવાપાત્ર ચોખ્ખી રકમ',charges:'કાંટા ખર્ચ (₹)',
    deductions:'અન્ય કપાત (₹)',adjust:'રાઉન્ડ ઓફ (₹)',post_bill:'ખરીદી પાવતી કન્ફર્મ કરો →'
  }
};
function t(key){
  const l=state.lang||'gu';
  return (I18N[l]&&I18N[l][key])||(I18N.en&&I18N.en[key])||key;
}
function applyLanguage(){
  if($('#lang-label'))$('#lang-label').textContent=state.lang==='gu'?'ગુજરાતી':'English';
  const navMap={dashboard:t('dashboard'),new:t('new'),purchases:t('purchases'),farmers:t('farmers'),payments:t('payments'),reports:t('reports'),users:t('users'),audit:t('audit')};
  $$('#navigation .nav').forEach(btn=>{
    const v=btn.dataset.view;
    if(navMap[v]){
      const nodes=btn.childNodes;
      nodes[nodes.length-1].textContent=' '+navMap[v];
    }
  });
  if(state.view&&$('#top-title')){
    $('#top-title').textContent=navMap[state.view]||state.view;
  }
}
function notify(message,kind='good'){const e=$('#notice');e.textContent=message;e.className='notice '+kind;e.hidden=false;clearTimeout(notify.t);notify.t=setTimeout(()=>e.hidden=true,6500)}
async function api(path,method='GET',body){let options={method,headers:{},credentials:'include'};if(body!==undefined){options.headers['Content-Type']='application/json';options.body=JSON.stringify(body)}if(!['GET','HEAD'].includes(method)&&state.csrf)options.headers['X-CSRF-Token']=state.csrf;if(state.token)options.headers['Authorization']='Bearer '+state.token;let r;try{r=await fetch('/api'+path,options)}catch{throw Error('Cannot reach the server. Check your internet connection. Do not submit the transaction repeatedly.')}let obj;try{obj=await r.json()}catch{throw Error('Invalid response from the server')}if(!r.ok){if(r.status===401&&path!=='/login'){showLogin()}throw Error(typeof obj.detail==='string'?obj.detail:'Request failed')}return obj}
function showLogin(){state.user=null;state.token='';state.csrf='';sessionStorage.removeItem('fkf_token');localStorage.removeItem('fkf_token');$('#shell').hidden=true;$('#login').hidden=false;$('#password').value=''}
async function setupLoggedInUser(me){state.user=me;if(me.csrf_token)state.csrf=me.csrf_token;$('#login').hidden=true;$('#shell').hidden=false;$('#user-name').textContent=me.name;$('#user-role').textContent=me.role;$('#users-nav').hidden=me.role!=='OWNER';$('#audit-nav').hidden=me.role!=='OWNER';applyLanguage();if($('#lang-toggle')){$('#lang-toggle').onclick=()=>{state.lang=state.lang==='gu'?'en':'gu';localStorage.setItem('fkf_lang',state.lang);applyLanguage();navigate(state.view||'dashboard')}};try{state.branches=await api('/branches')}catch{state.branches=[]}state.branch=me.role==='OWNER'?'':String(me.branch_id);const branchSelector=$('#branch-filter');branchSelector.innerHTML=(me.role==='OWNER'?choice('','All factories'): '')+state.branches.map(b=>choice(b.id,b.name)).join('');branchSelector.value=state.branch;branchSelector.disabled=me.role!=='OWNER';navigate('dashboard')}
async function initialize(){let me;try{me=await api('/me')}catch(e){showLogin();return}try{await setupLoggedInUser(me)}catch(err){console.error('Setup dashboard error:',err);$('#login').hidden=true;$('#shell').hidden=false;notify('Dashboard error: '+err.message,'bad')}}
$('#login-form').addEventListener('submit',async e=>{e.preventDefault();const btn=e.target.querySelector('button');btn.disabled=true;$('#login-error').hidden=true;try{const data=await api('/login','POST',{username:$('#username').value,password:$('#password').value});if(data.token){state.token=data.token;sessionStorage.setItem('fkf_token',data.token);localStorage.setItem('fkf_token',data.token)}if(data.csrf_token)state.csrf=data.csrf_token;if(data.user){await setupLoggedInUser(data.user)}else{await initialize()}}catch(err){$('#login-error').textContent=err.message;$('#login-error').hidden=false}finally{btn.disabled=false}});
$('#logout').onclick=async()=>{try{await api('/logout','POST',{})}finally{showLogin()}};
$('#branch-filter').onchange=e=>{state.branch=e.target.value;navigate(state.view)};
$('#mobile-menu').onclick=()=>$('#sidebar').classList.toggle('open');
$$('#navigation .nav').forEach(btn=>btn.onclick=()=>navigate(btn.dataset.view));
function $$(s){return Array.from(document.querySelectorAll(s))}
function navigate(view){state.view=view;$('#sidebar').classList.remove('open');$$('#navigation .nav').forEach(b=>b.classList.toggle('active',b.dataset.view===view));applyLanguage();$('#view').innerHTML='<div class="panel"><div class="empty">Loading…</div></div>';const f=({dashboard:renderDashboard,new:renderNew,purchases:renderPurchases,farmers:renderFarmers,payments:renderPayments,reports:renderReports,users:renderUsers,audit:renderAudit})[view];f().catch(err=>{$('#view').innerHTML=`<div class="notice bad">${text(err.message)}</div>`})}
function scope(){return state.branch?'?branch_id='+encodeURIComponent(state.branch):''}
function table(headers,rows,empty='No records found'){return `<div class="table-wrap"><table><thead><tr>${headers.map(h=>`<th>${text(h)}</th>`).join('')}</tr></thead><tbody>${rows.length?rows.join(''):`<tr><td class="empty" colspan="${headers.length}"><strong>${text(empty)}</strong>New records will appear here.</td></tr>`}</tbody></table></div>`}
async function renderDashboard(){let [d,all]=await Promise.all([api('/dashboard'+scope()),api('/purchases'+scope())]);$('#view').innerHTML=title('Purchasing overview','Live purchasing visibility across your authorized factories.',`<button class="primary" id="quick-new">+ New purchase</button>`)+`<div class="grid four"><div class="stat"><div class="kicker">Today’s purchases <span class="emoji">▤</span></div><div class="number">${d.today_bills}</div><div class="foot">Bills posted today</div></div><div class="stat"><div class="kicker">Today’s quantity <span class="emoji">♧</span></div><div class="number">${number(d.today_kg)} <small>kg</small></div><div class="foot">Net peanut weight</div></div><div class="stat"><div class="kicker">Today’s purchase value <span class="emoji">₹</span></div><div class="number">${money(d.today_value)}</div><div class="foot">After charges and adjustments</div></div><div class="stat"><div class="kicker">Outstanding payments <span class="emoji">◷</span></div><div class="number">${money(d.outstanding)}</div><div class="foot">Includes pending cheques / bank transfers</div></div></div><div class="grid two" style="margin-top:21px"><div class="panel"><h3>All-time purchasing</h3><div class="detail-grid"><div><small>Total bills</small><strong>${d.all_bills}</strong></div><div><small>Total net weight</small><strong>${number(d.all_kg)} kg</strong></div><div><small>Total payable</small><strong>${money(d.total_purchase_value)}</strong></div></div></div><div class="panel"><h3>Payment instruments</h3><div class="stat" style="border:0;box-shadow:none;padding:0"><div class="kicker">Cheque / bank transfer pending clearance</div><div class="number">${money(d.pending_instruments)}</div></div></div></div><div class="panel" style="margin-top:20px"><div class="row" style="justify-content:space-between"><h3>Recent purchase bills</h3><button class="secondary" id="all-purchases">View all →</button></div>${table(['Bill','Factory','Farmer','Date','Net kg','Payable'],all.slice(0,8).map(p=>`<tr><td><button class="link" data-bill="${p.id}">${text(p.number)}</button></td><td>${text(p.branch)}</td><td>${text(p.farmer)}</td><td>${text(p.date)}</td><td>${number(p.net_kg)}</td><td>${money(p.payable)}</td></tr>`),'No purchase bills yet')}</div>`;$('#quick-new').onclick=()=>navigate('new');$('#all-purchases').onclick=()=>navigate('purchases');wireBills()}
async function renderFarmers(){
  const canCreate=['OWNER','PURCHASE'].includes(state.user.role);
  $('#view').innerHTML=title('Farmer directory & Khata','One farmer directory shared between Himatnagar and Modasa with running account ledgers.',canCreate?'<button class="primary" id="add-farmer">+ Register farmer</button>':'')+`<div class="panel"><div class="filters"><input id="farmer-search" placeholder="Search farmer / village / mobile"></div><p class="help">Showing up to 100 matching farmers. Click "Khata / ખાતાવહી" on any farmer to view their complete statement, bills, and payments.</p><div id="farmers-table"></div></div>`;
  let current=0,timer;
  async function lookup(){let serial=++current;const q=$('#farmer-search').value.trim();const rows=await api('/farmers?limit=100&search='+encodeURIComponent(q));if(serial!==current)return;
    $('#farmers-table').innerHTML=table(
      ['Farmer ID','Farmer name','Village','Mobile','Cooperative','Ledger / ખાતાવહી'],
      rows.map(f=>`<tr>
        <td>${text(f.code)}</td>
        <td><strong>${text(f.name)}</strong></td>
        <td>${text(f.village)}</td>
        <td>${text(f.mobile||'—')}</td>
        <td>${text(f.cooperative||'—')}</td>
        <td><button class="secondary" data-farmer-khata="${f.id}">Khata / ખાતાવહી →</button></td>
      </tr>`),
      'No matching farmers'
    );
    $$('[data-farmer-khata]').forEach(btn=>{
      btn.onclick=()=>farmerKhataModal(+btn.dataset.farmerKhata).catch(e=>notify(e.message,'bad'));
    });
  }
  $('#farmer-search').oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>lookup().catch(e=>notify(e.message,'bad')),250)};
  if($('#add-farmer'))$('#add-farmer').onclick=farmerModal;
  await lookup();
}
function openModal(html){$('#modal-content').innerHTML=html;$('#modal').hidden=false}
function closeModal(){$('#modal').hidden=true;$('#modal-content').innerHTML=''}
$('#modal-close').onclick=closeModal;$('#modal').addEventListener('click',e=>{if(e.target.id==='modal')closeModal()});
function farmerModal(done){openModal(`<h2>Register farmer</h2><p class="muted">This profile can be used at either factory.</p><form id="farmer-form" class="grid"><div class="form-grid two"><label>Farmer full name *<input name="name" required minlength="2" maxlength="140"></label><label>Village *<input name="village" required minlength="2" maxlength="140"></label><label>Mobile<input name="mobile" maxlength="20" inputmode="tel"></label><label>Cooperative (optional)<input name="cooperative" maxlength="140"></label></div><div id="farmer-modal-error" class="error-text"></div><button class="primary">Save farmer</button></form>`);$('#farmer-form').onsubmit=async e=>{e.preventDefault();const b=e.target.querySelector('button');b.disabled=true;try{const fd=Object.fromEntries(new FormData(e.target));const farmer=await api('/farmers','POST',fd);closeModal();notify('Farmer registered successfully.');if(typeof done==='function')await done(farmer);else navigate('farmers')}catch(err){$('#farmer-modal-error').textContent=err.message}finally{b.disabled=false}}}
async function farmerKhataModal(farmerId, dateFrom='', dateTo=''){
  let params=new URLSearchParams();
  if(dateFrom)params.set('date_from',dateFrom);
  if(dateTo)params.set('date_to',dateTo);
  const data=await api(`/farmers/${farmerId}/ledger?`+params.toString());
  const f=data.farmer,s=data.summary;
  const canPay=['OWNER','ACCOUNTS'].includes(state.user.role)&&Number(s.unallocated_balance)>0;
  const entriesHtml=data.entries.length?data.entries.map(e=>{
    const isBill=e.type==='BILL';
    return `<tr>
      <td>${text(e.date)}</td>
      <td><strong>${isBill?`<button class="link" data-bill-ref="${text(e.ref)}">${text(e.ref)}</button>`:text(e.ref)}</strong></td>
      <td>${text(e.branch)}</td>
      <td>${text(e.description)}</td>
      <td style="color:#16a34a;font-weight:600">${Number(e.credit)>0?'+ '+money(e.credit):'—'}</td>
      <td style="color:#dc2626;font-weight:600">${Number(e.debit)>0?'− '+money(e.debit):'—'}</td>
      <td><span class="pill ${e.status==='CLEARED'?'cleared':e.status==='PENDING'?'pending':'bounced'}">${text(e.status)}</span></td>
      <td><strong>${money(e.running_balance)}</strong></td>
    </tr>`;
  }).join(''):`<tr><td colspan="8" style="text-align:center;padding:24px;color:var(--muted)">No transactions recorded in this period.</td></tr>`;

  openModal(`
    <div class="no-print">
      <div class="row" style="justify-content:space-between;padding-right:24px;margin-bottom:18px">
        <div>
          <span class="eyebrow">${text(f.code)} · FARMER KHATA</span>
          <h2 style="margin:2px 0">${text(f.name)}</h2>
          <small class="muted">${text(f.village)}${f.mobile?' · Mobile: '+text(f.mobile):''}${f.cooperative?' · Coop: '+text(f.cooperative):''}</small>
        </div>
        <div class="row" style="gap:8px">
          ${canPay?`<button class="primary" id="khata-pay-btn" style="background:#15803d;border-color:#15803d">+ Pay farmer (FIFO)</button>`:''}
          <button class="outline-btn" id="khata-print-btn">Print statement</button>
        </div>
      </div>
      <div class="grid four" style="margin-bottom:20px">
        <div class="stat" style="padding:14px">
          <div class="kicker">Total bills</div>
          <div class="number" style="font-size:22px;margin-top:6px">${s.total_bills}</div>
          <div class="foot">${number(s.total_net_kg)} kg (${s.total_bags} bags)</div>
        </div>
        <div class="stat" style="padding:14px">
          <div class="kicker">Total billed</div>
          <div class="number" style="font-size:22px;margin-top:6px">${money(s.total_billed)}</div>
          <div class="foot">Gross payable</div>
        </div>
        <div class="stat" style="padding:14px">
          <div class="kicker">Total paid</div>
          <div class="number" style="font-size:22px;margin-top:6px;color:#16a34a">${money(s.total_cleared_payments)}</div>
          <div class="foot">Cleared payments</div>
        </div>
        <div class="stat" style="padding:14px;background:#fef2f2;border-color:#fecaca">
          <div class="kicker" style="color:#991b1b">Outstanding balance</div>
          <div class="number" style="font-size:22px;margin-top:6px;color:#dc2626">${money(s.outstanding_balance)}</div>
          <div class="foot" style="color:#b91c1c">Pending clearance: ${money(s.total_pending_payments)}</div>
        </div>
      </div>
      <div class="panel" style="padding:14px;margin-bottom:16px;background:#fbf9f6">
        <div class="row" style="flex-wrap:wrap;gap:10px;align-items:flex-end">
          <label style="font-size:11px">From date
            <input type="date" id="khata-date-from" value="${data.date_from}">
          </label>
          <label style="font-size:11px">To date
            <input type="date" id="khata-date-to" value="${data.date_to}">
          </label>
          <button class="secondary" id="khata-filter-btn" style="padding:8px 14px">Filter dates</button>
          <button class="outline-btn" id="khata-reset-btn" style="padding:8px 14px">All history</button>
        </div>
      </div>
    </div>
    <div class="receipt" style="max-width:100%;padding:10px 0">
      <div class="receipt-header">
        <h2>Farmkart Foods</h2>
        <p>FARMER ACCOUNT KHATA STATEMENT · ખેડૂત ખાતાવહી</p>
        <p><strong>${text(f.name)}</strong> · ${text(f.village)} · ${text(f.code)}</p>
      </div>
      <div style="margin:14px 0;display:flex;justify-content:space-between;font-size:12px">
        <div>Statement Period: <strong>${data.date_from||'Beginning'} to ${data.date_to||'Today'}</strong></div>
        <div>Opening Balance: <strong>${money(data.opening_balance)}</strong></div>
        <div>Current Net Balance: <strong style="color:#dc2626">${money(data.closing_balance)}</strong></div>
      </div>
      <table>
        <thead>
          <tr>
            <th>Date</th><th>Ref / Bill</th><th>Factory</th><th>Particulars</th><th>Credit (+ જમા)</th><th>Debit (− ચૂકવણી)</th><th>Status</th><th>Balance</th>
          </tr>
        </thead>
        <tbody>
          ${data.date_from?`<tr style="background:#fdfcf9;font-style:italic"><td>${text(data.date_from)}</td><td>—</td><td>—</td><td>Opening balance brought forward</td><td>—</td><td>—</td><td>—</td><td><strong>${money(data.opening_balance)}</strong></td></tr>`:''}
          ${entriesHtml}
        </tbody>
        <tfoot>
          <tr style="background:#f8f6f2;font-weight:bold">
            <td colspan="4">Closing Balance</td>
            <td style="color:#16a34a">+ ${money(s.total_billed)}</td>
            <td style="color:#dc2626">− ${money(s.total_cleared_payments)}</td>
            <td>—</td>
            <td style="font-size:15px;color:#dc2626">${money(data.closing_balance)}</td>
          </tr>
        </tfoot>
      </table>
      <div class="receipt-foot">
        <small>Farmer Signature</small>
        <small>Farmkart Foods Accounts Signatory</small>
      </div>
    </div>
  `);
  $('#khata-print-btn').onclick=()=>window.print();
  $('#khata-filter-btn').onclick=()=>{
    const dFrom=$('#khata-date-from').value,dTo=$('#khata-date-to').value;
    farmerKhataModal(farmerId,dFrom,dTo);
  };
  $('#khata-reset-btn').onclick=()=>farmerKhataModal(farmerId);
  if($('#khata-pay-btn'))$('#khata-pay-btn').onclick=()=>farmerPaymentModal(data);
  $$('[data-bill-ref]').forEach(btn=>{
    btn.onclick=async()=>{
      const ref=btn.dataset.billRef;
      const b=await api('/purchases?search='+encodeURIComponent(ref));
      if(b.length)billModal(b[0].id);
    };
  });
}
function farmerPaymentModal(data){
  const f=data.farmer,s=data.summary;
  openModal(`
    <h2>Record farmer payment (FIFO allocation)</h2>
    <p class="muted">Payments are automatically distributed across the oldest unpaid purchase bills for <strong>${text(f.name)}</strong>.</p>
    <div class="panel" style="margin-bottom:16px;background:#fefbf8">
      <div class="row" style="justify-content:space-between">
        <div>Available Unallocated Balance:</div>
        <strong style="font-size:17px;color:#dc2626">${money(s.unallocated_balance)}</strong>
      </div>
    </div>
    <form id="farmer-pay-form" class="grid">
      <div class="form-grid two">
        <label>Payment Method *
          <select name="method" required>
            <option value="CASH">CASH (રોકડ - auto-cleared)</option>
            <option value="BANK">BANK TRANSFER / NEFT (બેંક ટ્રાન્સફર)</option>
            <option value="CHEQUE">CHEQUE (ચેક)</option>
          </select>
        </label>
        <label>Amount (₹) *
          <input name="amount" type="number" step="0.01" min="0.01" max="${Number(s.unallocated_balance)}" value="${Number(s.unallocated_balance)}" required>
        </label>
        <label>Instrument Date
          <input name="instrument_date" type="date">
        </label>
        <label>Reference / Cheque / UTR #
          <input name="reference" maxlength="100" placeholder="e.g. UTR-987654 or Chq 123456">
        </label>
      </div>
      <div id="farmer-pay-error" class="error-text"></div>
      <div class="row" style="justify-content:flex-end;gap:10px;margin-top:10px">
        <button type="button" class="outline-btn" id="cancel-farmer-pay">Cancel</button>
        <button type="submit" class="primary" id="submit-farmer-pay">Confirm & allocate payment →</button>
      </div>
    </form>
  `);
  $('#cancel-farmer-pay').onclick=()=>farmerKhataModal(f.id);
  $('#farmer-pay-form').onsubmit=async e=>{
    e.preventDefault();
    const btn=$('#submit-farmer-pay'),err=$('#farmer-pay-error');
    err.textContent='';
    btn.disabled=true;
    try{
      const fd=new FormData(e.target);
      const payload={
        idem_key:token(),
        method:fd.get('method'),
        amount:fd.get('amount'),
        reference:fd.get('reference')||'',
        instrument_date:fd.get('instrument_date')||null
      };
      const res=await api(`/farmers/${f.id}/payments`,'POST',payload);
      notify(`Paid ${money(res.total_paid)} allocated across ${res.allocations.length} bill(s).`);
      await farmerKhataModal(f.id);
    }catch(ex){
      err.textContent=ex.message;
      btn.disabled=false;
    }
  };
}
async function renderPurchases(){
  $('#view').innerHTML=title('Purchase register','Every posted bill has its own permanent factory-specific number.','<button id="new-from-reg" class="primary">+ New purchase</button>')+
    `<div class="panel">
      <div class="filters" style="display:flex;flex-wrap:wrap;gap:10px;align-items:center">
        <input id="bill-search" placeholder="Search bill #, farmer, village, RST, vehicle..." style="min-width:240px;flex:1">
        <select id="bill-factory">
          <option value="">All visible factories</option>
          ${state.branches.map(b=>choice(b.id,b.name)).join('')}
        </select>
        <select id="bill-status-filter">
          <option value="">All statuses</option>
          <option value="POSTED">POSTED (Active)</option>
          <option value="VOID">VOID (Cancelled)</option>
        </select>
        <div class="row" style="gap:6px;align-items:center">
          <input type="date" id="bill-date-from" title="From date" style="width:145px">
          <span style="color:var(--muted)">to</span>
          <input type="date" id="bill-date-to" title="To date" style="width:145px">
        </div>
        <div class="row" style="gap:4px">
          <button type="button" class="secondary" id="btn-today" style="padding:6px 10px;font-size:0.8rem">Today</button>
          <button type="button" class="secondary" id="btn-month" style="padding:6px 10px;font-size:0.8rem">Month</button>
          <button type="button" class="outline-btn" id="btn-clear-date" style="padding:6px 10px;font-size:0.8rem">Clear</button>
        </div>
      </div>
      <div id="purchase-count" style="margin:12px 0 6px;font-size:0.85rem;color:var(--muted)"></div>
      <div id="purchase-table"></div>
      <div id="purchase-load-more" style="text-align:center;margin-top:16px" hidden>
        <button class="secondary" id="load-more-btn">↓ Load more bills</button>
      </div>
    </div>`;

  $('#bill-factory').value=state.branch;
  let currentOffset=0;
  const pageSize=50;
  let allLoadedBills=[];
  let searchTimer;
  let fetchId=0;

  async function fetchBills(reset=true){
    const thisFetch=++fetchId;
    if(reset){
      currentOffset=0;
      allLoadedBills=[];
      $('#purchase-table').innerHTML='<div class="empty">Loading matching bills…</div>';
    }
    const q=$('#bill-search').value.trim();
    const branch=$('#bill-factory').value;
    const status=$('#bill-status-filter').value;
    const dFrom=$('#bill-date-from').value;
    const dTo=$('#bill-date-to').value;

    let params=new URLSearchParams();
    params.set('limit',String(pageSize));
    params.set('offset',String(currentOffset));
    if(branch) params.set('branch_id',branch);
    if(status) params.set('status',status);
    if(q) params.set('search',q);
    if(dFrom) params.set('date_from',dFrom);
    if(dTo) params.set('date_to',dTo);

    try{
      const data=await api('/purchases?'+params.toString());
      if(thisFetch!==fetchId)return;
      if(reset){
        allLoadedBills=data;
      }else{
        allLoadedBills=allLoadedBills.concat(data);
      }
      currentOffset+=data.length;
      
      $('#purchase-count').textContent=`Showing ${allLoadedBills.length} purchase bill${allLoadedBills.length===1?'':'s'}${dFrom||dTo?` (from ${dFrom||'earliest'} to ${dTo||'latest'})`:''}`;
      
      $('#purchase-table').innerHTML=table(
        ['Bill','Date','Factory','Farmer','Bags','Net kg','Payable','Status','Outstanding',''],
        allLoadedBills.map(p=>{
          const isVoid=p.status==='VOID';
          const stPill=isVoid
            ? `<span class="pill bounced">VOID</span>`
            : `<span class="pill cleared">POSTED</span>`;
          return `<tr style="${isVoid?'opacity:0.65;background:#fef2f2;':''}">
            <td><button class="link" data-bill="${p.id}">${text(p.number)}</button></td>
            <td>${text(p.date)}</td>
            <td>${text(p.branch)}</td>
            <td><strong>${text(p.farmer)}</strong><br><small>${text(p.village)}${p.mobile?' · '+text(p.mobile):''}</small></td>
            <td><strong>${p.total_bags||0}</strong></td>
            <td>${number(p.net_kg)}</td>
            <td>${money(p.payable)}</td>
            <td>${stPill}</td>
            <td>${isVoid?'—':money(p.payments_summary.outstanding)}</td>
            <td><button class="secondary" data-bill="${p.id}">Open</button></td>
          </tr>`;
        }),
        'No matching purchase bills found'
      );
      wireBills();
      
      const loadMoreWrap=$('#purchase-load-more');
      loadMoreWrap.hidden=data.length<pageSize;
    }catch(err){
      if(thisFetch===fetchId){
        $('#purchase-table').innerHTML=`<div class="notice bad">${text(err.message)}</div>`;
      }
    }
  }

  function queueSearch(){
    clearTimeout(searchTimer);
    searchTimer=setTimeout(()=>fetchBills(true),260);
  }

  $('#bill-search').oninput=queueSearch;
  $('#bill-factory').onchange=()=>fetchBills(true);
  $('#bill-status-filter').onchange=()=>fetchBills(true);
  $('#bill-date-from').onchange=()=>fetchBills(true);
  $('#bill-date-to').onchange=()=>fetchBills(true);

  $('#btn-today').onclick=()=>{
    const d=new Date().toISOString().split('T')[0];
    $('#bill-date-from').value=d;
    $('#bill-date-to').value=d;
    fetchBills(true);
  };
  $('#btn-month').onclick=()=>{
    const now=new Date();
    const firstDay=new Date(now.getFullYear(),now.getMonth(),1).toISOString().split('T')[0];
    const todayStr=now.toISOString().split('T')[0];
    $('#bill-date-from').value=firstDay;
    $('#bill-date-to').value=todayStr;
    fetchBills(true);
  };
  $('#btn-clear-date').onclick=()=>{
    $('#bill-date-from').value='';
    $('#bill-date-to').value='';
    fetchBills(true);
  };
  $('#load-more-btn').onclick=()=>fetchBills(false);
  $('#new-from-reg').onclick=()=>navigate('new');

  await fetchBills(true);
}
function wireBills(){$$('[data-bill]').forEach(b=>b.onclick=()=>billModal(+b.dataset.bill).catch(e=>notify(e.message,'bad')))}
let savedSubmission=null;
async function renderNew(){if(!['OWNER','PURCHASE'].includes(state.user.role)){$('#view').innerHTML='<div class="notice bad">You do not have permission to create purchase bills.</div>';return}const farmers=await api('/farmers?limit=60');state.farmers=farmers;state.lineCount=0;savedSubmission=token();$('#view').innerHTML=title('New purchase bill','Enter farmer details, peanut weights, bardana / bags, rate and deductions.')+`<form id="purchase-form" class="purchase-layout"><div class="grid"><div class="panel"><div class="row" style="justify-content:space-between;align-items:center;margin-bottom:12px"><div class="panel-subtitle" style="margin:0">01 / ખેડૂત અને આગમન વિગત (Farmer & arrival)</div><div id="next-bill-badge" style="background:#fef3c7;color:#92400e;border:1px solid #fcd34d;padding:4px 12px;border-radius:20px;font-weight:700;font-size:12px">બિલ નં: —</div></div><div class="form-grid two"><label>ફેક્ટરી (Factory) *<select id="purchase-branch" required>${state.branches.map(b=>choice(b.id,b.name,String(b.id)===state.branch)).join('')}</select></label><label>બિલ તારીખ (Bill Date) *<input id="bill-date" type="date" required></label><label>ખેડૂતનું નામ (Farmer Name) *<input id="farmer-name" list="farmer-datalist" required placeholder="ખેડૂતનું નામ લખો..." autocomplete="off"><datalist id="farmer-datalist">${farmers.map(f=>`<option value="${text(f.name)}" data-id="${f.id}" data-village="${text(f.village)}" data-mobile="${text(f.mobile||'')}">${text(f.name)} (${text(f.village)})</option>`).join('')}</datalist><input type="hidden" id="selected-farmer-id" value=""></label><label>ગામ (Village) *<input id="farmer-village" required placeholder="ગામનું નામ"></label><label>મોબાઈલ નંબર (Mobile No.)<input id="farmer-mobile" type="tel" maxlength="20" placeholder="મોબાઈલ નંબર"></label><label>RST / પાવતી નંબર (Pavati no.)<input id="rst" maxlength="80" placeholder="આગમન સંદર્ભ / વજન કાંટો નં"></label><label>વાહન નંબર (Vehicle no.)<input id="vehicle" maxlength="60" placeholder="GJ-…"></label></div></div><div class="panel"><div class="panel-subtitle">02 / Peanut purchase line items (કટ્ટા / બારદાન ગણતરી)</div><div id="purchase-lines"></div><button type="button" class="secondary" id="add-line">+ Add peanut variety / lot</button><p class="help">Bag tare is deducted automatically: Net kg = Gross kg − (Bags × Tare/bag + Kapat kg). Rates are ₹ per 20 kg.</p></div><div class="panel"><div class="panel-subtitle">03 / ખર્ચ અને કપાત (Charges & deductions)</div><div class="form-grid two"><label>કાંટા ખર્ચ — Weighbridge charges (₹)<input id="charges" type="number" value="0" min="0" step="0.01"></label><label>માર્કેટ / ટ્રાન્સપોર્ટ ખર્ચ — Market transport cost (₹)<input id="transport-cost" type="number" value="0" min="0" step="0.01" placeholder="0.00"></label><label>અન્ય કપાત — Other deductions (₹)<input id="deductions" type="number" value="0" min="0" step="0.01"></label><label>રાઉન્ડ ઓફ — Round adjustment (₹)<input id="adjust" type="number" value="0" step="0.01"></label><label style="display:flex;align-items:center;gap:10px;cursor:pointer;margin-top:6px;grid-column:1/-1;background:#fbf8f4;padding:12px;border-radius:8px;border:1px solid #ebdccb"><input id="unload-godown" type="checkbox" style="width:20px;height:20px;cursor:pointer;margin:0"><span style="font-size:13px;font-weight:700;color:#5a3e28">ગોડાઉન ઉતરાઈ (Unload at Go-down)</span></label><label style="grid-column:1/-1">નોંધ / રિમાર્ક્સ — Notes / remarks<textarea id="notes" rows="2" maxlength="1000" placeholder="ગુણવત્તા અથવા સ્પેશિયલ નોંધ..."></textarea></label></div></div><div class="panel payment-panel"><div class="panel-subtitle">ਪੇਮੇਨ੍ਟ ਸ੆ਟਲਮੇਨ੍ਟ (04 / Payment settlement)</div><div class="form-grid two"><label>ਆਜੇ ਚੂਕਵੇਲ ਰੋਕਡ — Paid today (Cash) ₹<input id="paid-cash" type="number" value="0" min="0" step="0.01" placeholder="0.00"></label><label>ਬਾਕੀ ਰੋਕਡ — Pay later (Cash) ₹<input id="pay-later-cash" type="number" value="0" min="0" step="0.01" placeholder="0.00"></label><label>ਬਾਕੀ ਰੋਕਡ ਤਾਰੀਖ — Pay later date<input id="pay-later-date" type="date"></label></div><div class="cheque-box"><div class="cheque-box-title">ਚੇਕ ਵਿਗਤ — Cheque details</div><div class="form-grid three"><label>ਚੇਕ ਨਂਬਰ — Cheque no.<input id="cheque-num" type="text" maxlength="30" placeholder="000001"></label><label>ਚੇਕ ਤਾਰੀਖ — Cheque date<input id="cheque-date" type="date"></label><label>ਚੇਕ ਰਕਮ — Cheque amount ₹<input id="cheque-amount" type="number" value="0" min="0" step="0.01" readonly class="cheque-auto-field"></label></div><div id="cheque-helper" class="cheque-helper"></div></div></div></div><div class="panel" style="position:sticky;top:15px"><div class="panel-subtitle">Live bill preview</div><div class="right-note">Final amounts will be recomputed and assigned a permanent bill number by the server.</div><div class="amount-box"><div class="amount-line"><span>Bags (કટ્ટા)</span><strong id="v-bags">0</strong></div><div class="amount-line"><span>Gross kg</span><strong id="v-gross">0</strong></div><div class="amount-line"><span>Bardana tare (kg)</span><strong id="v-bardana">0</strong></div><div class="amount-line"><span>Quality kapat (kg)</span><strong id="v-kapat">0</strong></div><div class="amount-line"><span>Net kg</span><strong id="v-net">0</strong></div><div class="amount-line"><span>Purchase value</span><strong id="v-value">₹0.00</strong></div><div class="amount-line"><span>Charges & deductions</span><strong id="v-deduct">₹0.00</strong></div><div class="amount-line final"><span>Farmer payable</span><span id="v-final">₹0.00</span></div></div><div class="pay-preview" id="pay-preview"><div class="pay-preview-title">ਚੂਕਵਣੀ ਸਾਰਾਂਸ਼ (Payment summary)</div><div class="amount-line"><span>ਆਜੇ ਰੋਕਡ (Cash today)</span><strong id="pv-cash">₹0.00</strong></div><div class="amount-line"><span>ਚੇਕ (Cheque)</span><strong id="pv-cheque">₹0.00</strong></div><div id="pv-cheque-line" class="amount-line" style="display:none"><span>ਚੇਕ ਵਿਗਤ</span><small id="pv-cheque-detail" style="color:var(--muted)"></small></div><div class="amount-line" style="border-top:1px solid #dfc7ba;margin-top:8px;padding-top:8px"><span>ਬਾਕੀ (Balance due)</span><strong id="pv-balance" style="color:#dc2626">₹0.00</strong></div></div><div id="bill-error" class="error-text"></div><button type="submit" class="primary full" id="post-bill" style="margin-top:16px">Post final purchase bill →</button><p class="right-note" style="margin-top:12px">Once posted, bills cannot be edited in this pilot. Verify all amounts before posting.</p></div></form>`;if(state.branch)$('#purchase-branch').value=state.branch;
  $('#add-line').onclick=()=>addLine();addLine();
  const todayISO=new Date().toISOString().split('T')[0];
  if($('#cheque-date'))$('#cheque-date').value=todayISO;
  if($('#bill-date'))$('#bill-date').value=todayISO;

  async function updateNextBillNumber(){
    const bId = $('#purchase-branch')?.value;
    const bDate = $('#bill-date')?.value || todayISO;
    if(bId){
      try{
        const seq = await api(`/purchases/next-number?branch_id=${bId}&purchase_date=${bDate}`);
        if($('#next-bill-badge')) $('#next-bill-badge').textContent = `બિલ નં: ${seq.formatted}`;
      }catch(e){}
    }
  }
  updateNextBillNumber();
  if($('#purchase-branch')) $('#purchase-branch').addEventListener('change', updateNextBillNumber);
  if($('#bill-date')) $('#bill-date').addEventListener('change', updateNextBillNumber);
  
  // Point 2: Farmer Datalist & Live Auto-fill
  const nameInput = $('#farmer-name');
  const villageInput = $('#farmer-village');
  const mobileInput = $('#farmer-mobile');
  const idInput = $('#selected-farmer-id');
  
  function checkFarmerMatch(){
    const val = nameInput.value.trim().toLowerCase();
    const match = state.farmers.find(f => f.name.toLowerCase() === val);
    if(match){
      idInput.value = match.id;
      if(!villageInput.value || villageInput.value === match.village) villageInput.value = match.village;
      if(!mobileInput.value || mobileInput.value === match.mobile) mobileInput.value = match.mobile || '';
    } else {
      idInput.value = '';
    }
  }

  let searchTimer;
  nameInput.addEventListener('input', () => {
    checkFarmerMatch();
    clearTimeout(searchTimer);
    searchTimer = setTimeout(async () => {
      const q = nameInput.value.trim();
      if(q.length >= 2){
        try{
          const results = await api('/farmers?limit=40&search='+encodeURIComponent(q));
          state.farmers = results;
          const dl = $('#farmer-datalist');
          if(dl){
            dl.innerHTML = results.map(f=>`<option value="${text(f.name)}">${text(f.name)} (${text(f.village)})</option>`).join('');
          }
          checkFarmerMatch();
        }catch(e){}
      }
    }, 250);
  });
  nameInput.addEventListener('change', checkFarmerMatch);

  $('#purchase-form').oninput=calculate;$('#purchase-form').onsubmit=submitBill}
function addLine(){if(state.lineCount>=25){notify('Maximum 25 items per bill.','bad');return}const idx=state.lineCount++;const e=document.createElement('div');e.className='item-grid';e.innerHTML=`<label>Variety<input class="line-variety" value="Java" maxlength="80" required list="varieties"><datalist id="varieties"><option value="Java"><option value="Bold"><option value="TJ"><option value="In-shell"><option value="Other"></datalist></label><label>Bags (કટ્ટા)<input class="line-bags" type="number" min="0" max="100000" step="1" value="0" placeholder="0"></label><label>Tare/bag (kg)<input class="line-tare" type="number" min="0" max="50" step="0.001" value="1.000" placeholder="1.000"></label><label>Gross kg<input class="line-gross" type="number" min="0.001" max="10000000" step="0.001" required placeholder="1000"></label><label>Kapat kg<input class="line-kapat" type="number" min="0" max="10000000" step="0.001" value="0" placeholder="0"></label><label>Rate / 20kg (₹)<input class="line-rate" type="number" min="0.01" max="10000000" step="0.01" required placeholder="2200"></label><button type="button" class="mini-button" title="Remove line">×</button>`;e.querySelector('button').onclick=()=>{e.remove();calculate()};$('#purchase-lines').append(e);calculate()}
function lines(){return $$('#purchase-lines .item-grid').map(r=>({variety:r.querySelector('.line-variety').value.trim(),bag_count:Math.max(0,parseInt(r.querySelector('.line-bags').value||0,10)),bag_tare_kg:r.querySelector('.line-tare').value||'0',gross_kg:r.querySelector('.line-gross').value,kapat_kg:r.querySelector('.line-kapat').value||'0',rate_per_20kg:r.querySelector('.line-rate').value}))}
function calculate(){const all=lines(),n=v=>Number(v||0);let totalBags=0,gross=0,bardana=0,qualityKapat=0,val=0;for(const x of all){const bags=n(x.bag_count);const tare=n(x.bag_tare_kg);const lineBardana=bags*tare;const lineQuality=n(x.kapat_kg);const lineTotalKapat=lineBardana+lineQuality;const lineGross=n(x.gross_kg);const lineNet=Math.max(0,lineGross-lineTotalKapat);const rate=n(x.rate_per_20kg);totalBags+=bags;gross+=lineGross;bardana+=lineBardana;qualityKapat+=lineQuality;val+=Math.round(lineNet*rate/20*100)/100}const totalKapat=bardana+qualityKapat;const net=Math.max(0,gross-totalKapat);const transportCost=n($('#transport-cost')?.value);const deduct=n($('#charges').value)+n($('#deductions').value)+transportCost;const end=val-deduct+n($('#adjust').value);if($('#v-bags'))$('#v-bags').textContent=totalBags;$('#v-gross').textContent=number(gross);if($('#v-bardana'))$('#v-bardana').textContent=number(bardana);$('#v-kapat').textContent=number(qualityKapat);$('#v-net').textContent=number(net);$('#v-value').textContent=money(val);$('#v-deduct').textContent=money(deduct);$('#v-final').textContent=money(end);
  // Point 1: auto-calc cheque = payable - cash paid
  const cashPaidEl=$('#paid-cash');const chequeEl=$('#cheque-amount');
  if(cashPaidEl&&chequeEl){
    const cashPaid=n(cashPaidEl.value);
    const autoChq=Math.max(0,Math.round((end-cashPaid)*100)/100);
    chequeEl.value=autoChq.toFixed(2);
    const helper=$('#cheque-helper');
    const gujaratiLabel='ਚੇਕ ਰਕਮ: ₹ ';
    if(helper)helper.textContent=autoChq>0?(gujaratiLabel+autoChq.toLocaleString('en-IN',{minimumFractionDigits:2})):'';
    const pvCash=$('#pv-cash');const pvCheque=$('#pv-cheque');
    const pvBal=$('#pv-balance');const pvChqLine=$('#pv-cheque-line');
    const pvChqDetail=$('#pv-cheque-detail');
    if(pvCash)pvCash.textContent=money(cashPaid);
    if(pvCheque)pvCheque.textContent=money(autoChq);
    const chqNum=$('#cheque-num')?.value.trim();
    const chqDate=$('#cheque-date')?.value;
    if(pvChqLine&&pvChqDetail){
      if(autoChq>0&&chqNum){
        pvChqLine.style.display='flex';
        pvChqDetail.textContent=chqNum+' | '+(chqDate||'—')+' | ₹'+autoChq.toLocaleString('en-IN',{minimumFractionDigits:2})
      }else pvChqLine.style.display='none'
    }
    const payLater=n($('#pay-later-cash')?.value);
    const balance=Math.max(0,Math.round((end-cashPaid-autoChq-payLater)*100)/100);
    if(pvBal)pvBal.textContent=money(balance)
  }
}
async function submitBill(e){e.preventDefault();const err=$('#bill-error');err.textContent='';const all=lines();if(!all.length){err.textContent='Add at least one peanut purchase line.';return}if(all.some(x=>(Number(x.bag_count||0)*Number(x.bag_tare_kg||0)+Number(x.kapat_kg||0))>=Number(x.gross_kg||0))){err.textContent='Total deductions (Bardana + Kapat) cannot equal or exceed gross weight.';return}const farmerName = $('#farmer-name')?.value.trim();
  const farmerVillage = $('#farmer-village')?.value.trim();
  const farmerMobile = $('#farmer-mobile')?.value.trim() || '';
  const selectedFarmerId = $('#selected-farmer-id')?.value ? Number($('#selected-farmer-id').value) : null;
  if(!farmerName || farmerName.length < 2){err.textContent='ખેડૂતનું નામ દાખલ કરો (Farmer name is required).';return}
  if(!farmerVillage || farmerVillage.length < 2){err.textContent='ગામનું નામ દાખલ કરો (Village is required).';return}if(!confirm('Post this purchase bill permanently? Verify weight, rate and farmer before continuing.'))return;const cashPaid2=$('#paid-cash')?.value||'0';const payLaterCash=$('#pay-later-cash')?.value||'0';const payLaterDate=$('#pay-later-date')?.value||null;const chequeNum=$('#cheque-num')?.value||'';const chequeDate=$('#cheque-date')?.value||null;const chequeAmt=$('#cheque-amount')?.value||'0';const body={idem_key:savedSubmission,branch_id:Number($('#purchase-branch').value),farmer_id:selectedFarmerId,farmer_name:farmerName,farmer_village:farmerVillage,farmer_mobile:farmerMobile,rst_number:$('#rst').value,vehicle_number:$('#vehicle').value,weighbridge_charges:$('#charges').value,other_deductions:$('#deductions').value,market_transport_cost:$('#transport-cost')?.value||'0',unload_at_godown:Boolean($('#unload-godown')?.checked),round_adjustment:$('#adjust').value,purchase_date:$('#bill-date')?.value||null,notes:$('#notes').value,lines:all,cash_paid:cashPaid2,pay_later_cash:payLaterCash,pay_later_date:payLaterDate,cheque_number:chequeNum,cheque_date:chequeDate,cheque_amount:chequeAmt};const btn=$('#post-bill');btn.disabled=true;btn.textContent='Posting bill…';try{const result=await api('/purchases','POST',body);notify(`Purchase bill ${result.purchase.number} saved.`);await billModal(result.purchase.id);savedSubmission=token();navigate('purchases')}catch(ex){err.textContent=ex.message+' If the connection failed, check the purchase register before retrying.'}finally{btn.disabled=false;btn.textContent='Post final purchase bill →'}}
async function billModal(id){
  const p=await api('/purchases/'+id);
  const isVoid=p.status==='VOID';
  const lines=p.lines.map(x=>`<tr><td>${text(x.variety)}</td><td>${x.bag_count||0}</td><td>${number(x.bag_tare_kg||0)}</td><td>${number(x.gross_kg)}</td><td>${number(x.kapat_kg)}</td><td>${number(x.net_kg)}</td><td>${money(x.rate_per_20kg)}</td><td>${money(x.amount)}</td></tr>`).join('');
  const pays=p.payments.map(pay=>`<tr><td>${text(pay.method)}</td><td>${money(pay.amount)}</td><td>${text(pay.reference||'—')}</td><td>${text(pay.status)}</td></tr>`).join('');
  const canVoid=!isVoid && ['OWNER','PURCHASE'].includes(state.user.role);
  openModal(`
    <div class="no-print">
      <div class="row" style="justify-content:space-between;padding-right:24px;margin-bottom:18px">
        <h3>Purchase bill ${text(p.number)} ${isVoid?'<span class="pill bounced">VOIDED</span>':''}</h3>
        <div class="row" style="gap:8px">
          ${canVoid?`<button class="outline-btn" style="color:var(--bad, #dc2626);border-color:var(--bad, #dc2626)" id="void-bill-btn">Cancel / Void bill</button>`:''}
          <button class="outline-btn" style="background:#fefbf6;border-color:#b45309;color:#b45309;font-weight:700" id="print-thermal">🖨 80mm Thermal (થર્મલ)</button>
          <button class="primary" id="print-bill">Print receipt (A4/A5)</button>
        </div>
      </div>
      ${isVoid?`<div class="callout" style="border-left-color:var(--bad, #dc2626);background:#fee2e2;color:#991b1b;font-weight:600;margin-bottom:16px">⚠ THIS BILL HAS BEEN VOIDED / CANCELLED. All weights and balances are excluded from accounting and live reports.</div>`:''}
    </div>
    <div class="receipt ${isVoid?'voided':''}">
      ${isVoid?`<div style="text-align:center;color:#dc2626;font-size:1.3rem;font-weight:bold;letter-spacing:2px;border:2px dashed #dc2626;padding:6px;margin-bottom:14px">VOIDED / રદ કરેલ</div>`:''}
      <div class="receipt-header">
        <h2>Farmkart Foods · ફાર્મકાર્ટ ફૂડ્સ</h2>
        <p>PEANUT PURCHASE RECEIPT · મગફળી ખરીદી પાવતી</p>
        <p>Factory / ફેક્ટરી: <strong>${text(p.branch)}</strong></p>
      </div>
      <div class="receipt-grid">
        <div>Bill no. / બિલ નં: <strong>${text(p.number)}</strong></div>
        <div>Date / તારીખ: <strong>${text(p.date)}</strong></div>
        <div>Farmer / ખેડૂત: <strong>${text(p.farmer)}</strong></div>
        <div>Village / ગામ: <strong>${text(p.village)}</strong></div>
        <div>Mobile / મો.: <strong>${text(p.mobile||'—')}</strong></div>
        <div>RST / Pavati: <strong>${text(p.rst||'—')}</strong></div>
        <div>Vehicle / વાહન: <strong>${text(p.vehicle||'—')}</strong></div>
        <div>Total bags / કટ્ટા: <strong>${p.total_bags||0}</strong></div>
      </div>
      <table>
        <thead><tr><th>Peanut variety<br>મગફળી જાત</th><th>Bags<br>કટ્ટા</th><th>Tare/bag<br>બારદાન</th><th>Gross kg<br>કુલ વજન</th><th>Kapat kg<br>કપાત</th><th>Net kg<br>ચોખ્ખું</th><th>₹ / 20kg<br>ભાવ/મણ</th><th>Amount<br>રકમ</th></tr></thead>
        <tbody>${lines}</tbody>
      </table>
      <div style="max-width:340px;margin-left:auto;margin-top:18px">
        <div class="amount-line"><span>Gross purchase / કુલ ખરીદી</span><strong>${money(p.gross_value)}</strong></div>
        <div class="amount-line"><span>Weighbridge / કાંટા ખર્ચ</span><strong>− ${money(p.weighbridge_charges)}</strong></div>
        ${Number(p.market_transport_cost||0)>0?`<div class="amount-line"><span>Transport / માર્કેટ ખર્ચ</span><strong>− ${money(p.market_transport_cost)}</strong></div>`:''}
        <div class="amount-line"><span>Other deduction / અન્ય કપાત</span><strong>− ${money(p.other_deductions)}</strong></div>
        ${p.unload_at_godown?`<div class="amount-line" style="color:#b45309"><span>Delivery / વિગત</span><strong>ગોડાઉન ઉતરાઈ (Godown Unload)</strong></div>`:''}
        <div class="amount-line"><span>Round adjustment / રાઉન્ડ ઓફ</span><strong>${money(p.round_adjustment)}</strong></div>
        <div class="amount-line final"><span>Farmer payable / ચોખ્ખી ચૂકવવાપાત્ર રકમ</span><strong>${money(p.payable)}</strong></div>
      </div>
      ${p.notes?`<div style="margin-top:14px;font-size:0.85rem;color:var(--muted);white-space:pre-wrap"><strong>Notes / નોંધ:</strong> ${text(p.notes)}</div>`:''}
      <div class="receipt-foot">
        <small>ખેડૂત સહી (Farmer signature)</small>
        <small>અધિકૃત સહી (Authorized signatory)</small>
      </div>
      <p class="help" style="text-align:center">Computer-generated receipt · કમ્પ્યુટર જનરેટેડ ખરીદી પાવતી</p>
    </div>
    <div class="no-print">
      <div class="divider"></div>
      <h3>Payment status</h3>
      <div class="detail-grid">
        <div><small>Cleared</small><strong>${money(p.payments_summary.cleared)}</strong></div>
        <div><small>Pending</small><strong>${money(p.payments_summary.pending)}</strong></div>
        <div><small>Outstanding</small><strong>${money(p.payments_summary.outstanding)}</strong></div>
      </div>
      ${table(['Method','Amount','Reference','Status'],pays? p.payments.map(pay=>`<tr><td>${text(pay.method)}</td><td>${money(pay.amount)}</td><td>${text(pay.reference||'—')}</td><td>${text(pay.status)}</td></tr>`):[],'No payment entries')}
      ${!isVoid && ['OWNER','ACCOUNTS'].includes(state.user.role)&&Number(p.payments_summary.unallocated)>0?`<button id="record-payment" class="primary" style="margin-top:17px">+ Record payment</button>`:''}
    </div>
  `);
  function printThermalReceipt(){
    document.body.classList.add('printing-thermal');
    const r=$('.receipt');
    if(r)r.classList.add('thermal-receipt');
    window.print();
    setTimeout(()=>{
      document.body.classList.remove('printing-thermal');
      if(r)r.classList.remove('thermal-receipt');
    },1000);
  }
  $('#print-bill').onclick=()=>window.print();
  $('#print-thermal').onclick=()=>printThermalReceipt();
  if($('#record-payment'))$('#record-payment').onclick=()=>paymentModal(p);
  if($('#void-bill-btn'))$('#void-bill-btn').onclick=()=>voidBillModal(p.id,p.number);
}

function voidBillModal(id,number){
  openModal(`<h2>Void purchase bill</h2>
    <p class="muted">Bill <strong>${text(number)}</strong></p>
    <div class="callout" style="border-left-color:var(--bad, #dc2626);background:#fee2e2;color:#991b1b">
      <strong>Warning:</strong> Voiding this bill will permanently cancel it, exclude its weight and payable amount from all factory totals, and record an audit log. Any pending cheques or transfers will be cancelled. Bills with cleared payments cannot be cancelled.
    </div>
    <form id="void-form" style="margin-top:16px">
      <label>Cancellation reason (required) *
        <textarea name="reason" id="void-reason" required minlength="5" maxlength="500" rows="3" placeholder="e.g. Weighbridge clerk entered incorrect weight; re-issuing new slip."></textarea>
      </label>
      <p id="void-error" class="error-text"></p>
      <div class="row" style="gap:10px;margin-top:16px">
        <button type="submit" class="primary" style="background:var(--bad, #dc2626)">Confirm & void bill</button>
        <button type="button" class="secondary" id="void-cancel-btn">Back</button>
      </div>
    </form>`);
  $('#void-cancel-btn').onclick=()=>billModal(id);
  $('#void-form').onsubmit=async e=>{
    e.preventDefault();
    const btn=e.target.querySelector('button[type="submit"]');
    btn.disabled=true;
    $('#void-error').textContent='';
    try{
      const reason=$('#void-reason').value.trim();
      await api(`/purchases/${id}/void`,'POST',{reason});
      notify(`Bill ${number} has been voided.`);
      await billModal(id);
      if(state.view==='purchases')navigate('purchases');
    }catch(err){
      $('#void-error').textContent=err.message;
    }finally{
      btn.disabled=false;
    }
  };
}
function paymentModal(bill){openModal(`<h2>Record farmer payment</h2><p class="muted">Bill <strong>${text(bill.number)}</strong> · ${text(bill.farmer)}</p><div class="callout">Unallocated payable: <strong>${money(bill.payments_summary.unallocated)}</strong>. A cheque or bank transfer will remain pending until cleared.</div><form id="payment-form"><div class="form-grid two" style="margin-top:20px"><label>Payment method<select name="method" id="pay-method">${choice('CASH','Cash')}${choice('CHEQUE','Cheque')}${choice('BANK','Bank transfer')}</select></label><label>Amount ₹<input name="amount" value="${text(bill.payments_summary.unallocated)}" type="number" min="0.01" step="0.01" max="${text(bill.payments_summary.unallocated)}" required></label><label>Cheque / bank reference<input name="reference" maxlength="100" placeholder="Cheque number or UTR"></label><label>Instrument date<input name="instrument_date" type="date"></label></div><p id="payment-error" class="error-text"></p><button class="primary" style="margin-top:15px">Record payment</button></form>`);$('#payment-form').onsubmit=async e=>{e.preventDefault();const body=Object.fromEntries(new FormData(e.target));body.idem_key=paymentToken;body.instrument_date=body.instrument_date||null;try{await api('/purchases/'+bill.id+'/payments','POST',body);notify('Payment recorded.');await billModal(bill.id)}catch(ex){$('#payment-error').textContent=ex.message}};const paymentToken=token()}
async function renderPayments(){const payments=await api('/payments'+scope());$('#view').innerHTML=title('Cheques & payments','Review issued cheques, bank transfers, cash and clearance status.')+`<div class="panel"><div class="filters"><select id="pay-filter"><option value="">All payments</option><option value="PENDING">Pending clearance</option><option value="CLEARED">Cleared</option><option value="BOUNCED">Bounced</option></select></div><div id="payment-table"></div><p class="help">Only accounts and owner roles can record or finalize payments. Cash is cleared at entry; cheques and bank transfers need confirmation.</p></div>`;function display(){const f=$('#pay-filter').value,pp=payments.filter(p=>!f||p.status===f);$('#payment-table').innerHTML=table(['Bill','Farmer','Method','Reference','Amount','Status','Action'],pp.map(p=>`<tr><td><button class="link" data-bill="${p.purchase_id}">${text(p.bill_number)}</button></td><td>${text(p.farmer)}</td><td>${text(p.method)}</td><td>${text(p.reference||'—')}</td><td>${money(p.amount)}</td><td><span class="pill ${text(p.status.toLowerCase())}">${text(p.status)}</span></td><td>${p.status==='PENDING'&&['OWNER','ACCOUNTS'].includes(state.user.role)?`<button class="secondary" data-clear="${p.id}">Set status</button>`:'—'}</td></tr>`),'No payments yet');wireBills();$$('[data-clear]').forEach(b=>b.onclick=()=>statusModal(+b.dataset.clear))}$('#pay-filter').onchange=display;display()}
function statusModal(id){openModal(`<h2>Update payment status</h2><p class="muted">Mark this cheque or bank transfer only after checking bank evidence.</p><div class="grid"><button id="mark-cleared" class="primary">Mark cleared</button><button id="mark-bounced" class="secondary">Mark bounced / failed</button></div><p id="status-error" class="error-text"></p>`);for(const [selector,status] of [['#mark-cleared','CLEARED'],['#mark-bounced','BOUNCED']])$(selector).onclick=async()=>{if(!confirm('Confirm that the instrument status is '+status+'?'))return;try{await api('/payments/'+id+'/status','POST',{status});closeModal();notify('Payment status updated.');navigate('payments')}catch(e){$('#status-error').textContent=e.message}}}
async function renderReports(){const d=await api('/dashboard'+scope());$('#view').innerHTML=title('Reports & exports','Download your authorized factory purchase records and reconcile accounts.')+`<div class="grid two"><div class="panel"><div class="eyebrow">PURCHASE REGISTER</div><h3>Export all purchase bills</h3><p class="muted">CSV compatible with Excel. Includes farmer name, weights, payable, cleared, pending and outstanding.</p><button id="export-btn" class="primary">↓ Download purchase CSV</button></div><div class="panel"><div class="eyebrow">CURRENT REPORT</div><h3>Purchase summary</h3><div class="detail-grid"><div><small>Total bills</small><strong>${d.all_bills}</strong></div><div><small>Net kg</small><strong>${number(d.all_kg)}</strong></div><div><small>Payable</small><strong>${money(d.total_purchase_value)}</strong></div></div></div></div><div class="callout" style="margin-top:19px">Exports are generated server-side and restricted to authorized factory data. Full accounting integration and statutory reporting require additional configuration.</div>`;$('#export-btn').onclick=()=>{window.location.href='/api/export/purchases'+scope()}}
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
