/* The browser displays API results. All allocation and settlement rules stay on the server. */
"use strict";
const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const money = (value) => new Intl.NumberFormat("en-IN", {style:"currency",currency:"INR",maximumFractionDigits:2}).format(value ?? 0);
const magnitude = (value) => String(value ?? "0.00").replace(/^-/u, "");
const dateLabel = (value) => new Intl.DateTimeFormat("en-IN", {day:"numeric",month:"short",year:"numeric",timeZone:state.group?.timezone || "Asia/Kolkata"}).format(new Date(value));
const categories = ["travel","food","accommodation","activities","shopping","other"];
const state = {groups:[],group:null,members:[],tab:"overview",userId:null,offset:0,historyOffset:0,mode:"simplified",filters:{},reportFilters:{},request:0};
let modalSave, searchTimer, searchVersion = 0;

async function api(path, method="GET", body) {
  const response = await fetch(`/api/v1${path}`, {method,headers:body ? {"Content-Type":"application/json"} : {},body:body ? JSON.stringify(body) : undefined});
  const data = await response.json();
  if (!response.ok) {
    const details = data.error?.details?.map(d => `${d.location?.join(".")}: ${d.message}`).join("; ");
    throw new Error(details || data.error?.message || `Request failed (${response.status})`);
  }
  return data;
}
async function all(path) {
  const items = [];
  for (let offset=0; ; offset+=100) {
    const page = await api(`${path}${path.includes("?") ? "&" : "?"}limit=100&offset=${offset}`);
    items.push(...page.items);
    if (items.length >= page.total || !page.items.length) return items;
  }
}
function notice(message, error=false) { const node=$("#notice"); node.textContent=message; node.className=error ? "error" : ""; node.hidden=false; }
function empty(message) {return `<p class="empty">${esc(message)}</p>`;}
function person(name) {return `<span class="avatar" aria-hidden="true">${esc(name.slice(0,2).toUpperCase())}</span>`;}
function options(items, selected) {return items.map(i=>`<option value="${i.id}" ${Number(selected)===i.id ? "selected" : ""}>${esc(i.name)} (#${i.id})</option>`).join("");}
function categoryOptions(selected, automatic=false) {return `<option value="">${automatic ? "Suggest from description" : "All categories"}</option>`+categories.map(c=>`<option ${c===selected ? "selected" : ""} value="${c}">${c[0].toUpperCase()+c.slice(1)}</option>`).join("");}
function metric(label, value, caption, featured=false) {return `<div class="metric ${featured ? "featured" : ""}"><p class="metric-label">${esc(label)}</p><p class="metric-value">${money(value)}</p><small>${esc(caption)}</small></div>`;}
function pagination(offset,total,kind) {return `<div class="pagination"><span>${total ? offset+1 : 0}–${Math.min(offset+20,total)} of ${total}</span><button data-page="${kind}" data-offset="${offset-20}" ${offset===0 ? "disabled" : ""}>← Previous</button><button data-page="${kind}" data-offset="${offset+20}" ${offset+20>=total ? "disabled" : ""}>Next →</button></div>`;}
function renderGroups() {
  $("#group-list").innerHTML=state.groups.length ? state.groups.map(g=>`<button class="group-item ${g.id===state.group?.id ? "active" : ""}" data-group="${g.id}" ${g.id===state.group?.id ? 'aria-current="true"' : ""}><span class="group-icon">↗</span><span><strong>${esc(g.name)}</strong><small>${g.member_count} people · INR</small></span></button>`).join("") : empty("No trips yet. Create a group or try a demo trip.");
}
async function loadGroups(preferred) {
  state.groups=await all("/groups");
  renderGroups();
  const requested=Number(preferred || new URLSearchParams(location.search).get("group"));
  const selected=state.groups.find(g=>g.id===requested) || state.groups.find(g=>g.name==="Goa Trip (demo)") || state.groups[0];
  if (selected) await selectGroup(selected.id);
  else {$("#workspace").innerHTML=empty("Start with ‘Create a fresh demo trip’ to explore real results.");$("#add-expense").disabled=true;}
}
async function selectGroup(id) {
  let selected=state.groups.find(g=>g.id===id);
  if(!selected){selected=await api(`/groups/${id}`);state.groups.push(selected);}
  state.group=selected;
  $("#notice").hidden=true;
  state.userId=null;state.members=[];state.offset=0;state.historyOffset=0;state.filters={};state.reportFilters={};
  const url=new URL(location.href);url.searchParams.set("group",id);history.replaceState(null,"",url);
  renderGroups();$("#group-title").textContent=state.group.name;$("#breadcrumb-group").textContent=state.group.name;
  $("#group-subtitle").textContent=`${state.group.member_count} people · INR · ${state.group.timezone}`;
  await refresh();
}
async function refresh() {
  if (!state.group) return;
  const version=++state.request, groupId=state.group.id;
  $("#workspace").setAttribute("aria-busy","true");$("#add-expense").disabled=true;
  try {
    const members=await all(`/groups/${groupId}/members`);
    if (version!==state.request) return;
    state.members=members;
    if (!members.some(m=>m.id===state.userId)) state.userId=members[0]?.id;
    const html=await ({overview:overview,expenses:expenses,settle:settlements,members:membersView}[state.tab])();
    if (version!==state.request) return;
    $("#workspace").innerHTML=html;
  } catch(error) {if(version===state.request){notice(error.message,true);$("#workspace").innerHTML=empty("Couldn't load this view. Check the connection and try Refresh.")+`<button data-refresh>Refresh</button>`;}}
  finally {if(version===state.request){$("#workspace").setAttribute("aria-busy","false");$("#add-expense").disabled=!state.members.length;}}
}
function reportQuery() {return new URLSearchParams(Object.entries(state.reportFilters).filter(([,v])=>v)).toString();}
async function overview() {
  const id=state.group.id, query=reportQuery();
  const [group,balances,personal]=await Promise.all([api(`/groups/${id}/analytics?${query}`),api(`/groups/${id}/balances?view=net`),state.userId ? api(`/users/${state.userId}/analytics?group_id=${id}&${query}`) : null]);
  const position=balances.balances.find(b=>b.user.id===state.userId)?.amount || "0.00";
  const bars=group.categories.filter(c=>Number(c.amount)>0).map(c=>`<div class="category-row"><div class="row-top"><span>${esc(c.label)}</span><strong>${money(c.amount)} <span class="subtle">· ${esc(c.percentage)}%</span></strong></div><div class="track"><div class="fill ${esc(c.key)}" style="width:${Math.max(0,Math.min(100,Number(c.percentage)||0))}%"></div></div></div>`).join("");
  return `<form id="report-filter" class="filter-row"><label>From (inclusive)<input name="from" type="date" value="${esc(state.reportFilters.from||"")}"></label><label>To (exclusive)<input name="to" type="date" value="${esc(state.reportFilters.to||"")}"></label><button>Apply dates</button><button type="button" data-clear-dates>All time</button></form>
    <div class="view-as"><label for="view-user">Personal view</label><select id="view-user">${options(state.members,state.userId)}</select><span class="subtle">${personal ? "See each person's share and cash paid" : "Add a member to start"}</span></div>
    <div class="metrics">${metric("Total trip spending",group.totals.spending,"Selected period · all members",true)}${metric("Your share",personal?.totals.spending,"What you consumed in this period")}${metric("You paid",personal?.totals.paid,"Bills you paid in this period")}${metric(Number(position)<0 ? "You owe" : "You get back",magnitude(position),"Outstanding · all-time balance")}</div>
    <div class="grid"><section class="card"><div class="card-head"><h2>Where the money went</h2><span class="subtle">By category</span></div>${bars||empty("Add an expense to see your spending breakdown.")}<p class="legend">Categories are suggested from the description. You can always correct them.</p></section>
    <section class="card"><div class="card-head"><h2>Everyone's balance</h2><button data-open-tab="settle">Settle up ↗</button></div>${balances.balances.map(b=>`<div class="person-row">${person(b.user.name)}<div class="person-name">${esc(b.user.name)}<small>${Number(b.amount)>0 ? "Gets back" : Number(b.amount)<0 ? "Owes the group" : "All settled"}</small></div><span class="amount ${Number(b.amount)<0 ? "negative" : "positive"}">${money(magnitude(b.amount))}</span></div>`).join("")||empty("No outstanding balances. You're all square.")}<p>Balances include all recorded repayments, regardless of the report dates.</p></section></div>
    <section class="card"><div class="card-head"><h2>Biggest expenses</h2><button data-open-tab="expenses">View history ↗</button></div>${expenseRows(group.largest_expenses,true)}</section>
    <div class="grid" style="margin-top:22px"><section class="card"><div class="card-head"><h2>Spending over time</h2><span class="subtle">${esc(group.timezone)}</span></div>${group.months.filter(m=>Number(m.amount)>0).map(m=>`<div class="person-row"><span class="person-name">${esc(m.label)}</span><span class="amount">${money(m.amount)}</span></div>`).join("")||empty("No spending in this period.")}</section><section class="card"><h2>Your cash flow</h2><p>Consumption and payments answer different questions.</p>${[ ["Your allocated spending",personal?.totals.spending],["Bills paid",personal?.totals.paid],["Repayments sent",personal?.totals.settlements_sent],["Repayments received",personal?.totals.settlements_received],["Net cash outflow",personal?.totals.net_cash_outflow] ].map(([label,amount])=>`<div class="person-row"><span class="person-name">${label}</span><span class="amount">${money(amount)}</span></div>`).join("")}</section></div>`;
}
function expenseRows(rows, analytics=false) {
  if (!rows.length) return empty("No expenses here yet. Add one to start sharing.");
  return `<div class="table-scroll"><table><thead><tr><th>EXPENSE</th><th>PAID BY</th><th>CATEGORY</th><th>AMOUNT</th>${analytics ? "" : "<th>DETAILS</th>"}</tr></thead><tbody>${rows.map(e=>`<tr><td><strong>${esc(e.description)}</strong><small>${dateLabel(e.occurred_at)}</small></td><td>${esc(e.paid_by.name)}</td><td>${analytics ? `<span class="badge">${esc(e.category)}</span>` : `<select class="inline-select" data-category="${e.id}" aria-label="Category for ${esc(e.description)}">${categories.map(c=>`<option value="${c}" ${e.category===c ? "selected" : ""}>${c}</option>`).join("")}</select><small>${esc(e.category_source)} · ${esc(e.category_rule||"your choice")}</small>`}</td><td class="amount">${money(e.amount)}</td>${analytics ? "" : `<td><button data-detail="${e.id}">View split</button></td>`}</tr>`).join("")}</tbody></table></div>`;
}
async function expenses() {
  const query=new URLSearchParams({...state.filters,limit:20,offset:state.offset});
  const page=await api(`/groups/${state.group.id}/expenses?${query}`);
  return `<section class="card"><div class="card-head"><h2>Expense history</h2><span class="subtle">${page.total} expenses</span></div><form id="expense-filter" class="filter-row"><label>Description<input name="q" maxlength="100" placeholder="e.g. Dinner" value="${esc(state.filters.q||"")}"></label><label>Category<select name="category">${categoryOptions(state.filters.category)}</select></label><button>Filter</button></form>${expenseRows(page.items)}${pagination(state.offset,page.total,"expenses")}</section>`;
}
async function settlements() {
  const id=state.group.id;
  const [plan,history]=await Promise.all([api(`/groups/${id}/settlement-suggestions?mode=${state.mode}`),api(`/groups/${id}/settlements?limit=20&offset=${state.historyOffset}`)]);
  return `<section class="card"><div class="card-head"><h2>A clear path to all square</h2><select id="settlement-mode" style="width:auto" aria-label="Settlement suggestion mode"><option value="simplified" ${state.mode==="simplified" ? "selected" : ""}>Fewer payments</option><option value="direct" ${state.mode==="direct" ? "selected" : ""}>Keep original creditors</option></select></div><p>${esc(plan.explanation)}</p><p class="subtle">${plan.transaction_count} suggested payments · ${esc(plan.strategy)} strategy · ${plan.optimality_guaranteed ? "Minimum transaction count guaranteed" : "Minimum transaction count not guaranteed"}</p>${plan.transfers.length ? plan.transfers.map(t=>`<div class="transfer">${person(t.from_user.name)}<div class="transfer-content"><strong>${esc(t.from_user.name)}</strong> → <strong>${esc(t.to_user.name)}</strong><small>Pay externally, then record the repayment below</small></div><span class="amount">${money(t.amount)}</span><button class="primary" data-pay-from="${t.from_user.id}" data-pay-to="${t.to_user.id}" data-pay-amount="${esc(t.amount)}">Record payment</button></div>`).join("") : `<div class="success-card"><h3>You're all square.</h3><p>No payments needed. Add another shared expense whenever you're ready.</p></div>`}<p class="explanation">Suggestions do not move money. Recording a payment changes this demo's live balances. Each payment is checked against the latest debt before it is saved.</p></section><section class="card" style="margin-top:22px"><div class="card-head"><h2>Recorded repayments</h2><span class="subtle">${history.total} payments</span></div>${history.items.map(t=>`<div class="person-row">${person(t.from_user.name)}<div class="person-name">${esc(t.from_user.name)} → ${esc(t.to_user.name)}<small>${dateLabel(t.occurred_at)} · ${esc(t.note||t.mode)}</small></div><span class="amount">${money(t.amount)}</span></div>`).join("")||empty("No repayments recorded yet.")}${pagination(state.historyOffset,history.total,"history")}</section>`;
}
async function membersView() {
  return `<section class="card"><div class="card-head"><h2>The people behind the trip</h2><button id="add-member">+ Add person</button></div>${state.members.map(m=>`<div class="person-row">${person(m.name)}<div class="person-name">${esc(m.name)}<small>User #${m.id} · Joined ${dateLabel(m.joined_at)}</small></div><span class="badge">Member</span></div>`).join("")||empty("Add people before recording an expense.")}<p>New expenses include all current members. Adding a person never changes the shares saved on older expenses.</p></section>`;
}
function openModal(title,fields,save,label="Save") {
  $("#modal-title").textContent=title;$("#modal-fields").innerHTML=fields;$("#form-error").textContent="";$("#save-modal").textContent=label;modalSave=save;$("#modal").showModal();
}
async function saveAndRefresh(message) {$("#modal").close();notice(message);await refresh();}
function expenseModal() {
  const group=state.group.id, members=[...state.members];
  openModal("Add a shared expense",`<label>Description<input name="description" required maxlength="500" placeholder="e.g. Taxi to the beach"></label><label>Amount (INR)<input name="amount" type="number" min="0.01" max="10000000" step="0.01" required placeholder="1200.00"></label><label>Paid by<select name="paid_by">${options(members,state.userId)}</select></label><label>Split<select name="split_type" id="split-type"><option value="equal">Equally among all ${members.length} members</option><option value="custom">Custom amounts</option></select></label><div id="custom-splits" hidden><p>Include everyone; zero is allowed. Shares must add up to the bill.</p>${members.map(m=>`<label class="split-row">${esc(m.name)} (#${m.id})<input name="share_${m.id}" type="number" min="0" max="10000000" step="0.01" placeholder="0.00" aria-label="Share for ${esc(m.name)}"></label>`).join("")}</div><label>Category<select name="category">${categoryOptions("",true)}</select></label>`, async form=>{
    const body={description:form.get("description"),amount:form.get("amount"),paid_by:Number(form.get("paid_by")),split_type:form.get("split_type")};
    if(form.get("category"))body.category=form.get("category");
    if(body.split_type==="custom")body.splits=members.map(m=>({user_id:m.id,amount:form.get(`share_${m.id}`)||"0.00"}));
    await api(`/groups/${group}/expenses`,"POST",body);await saveAndRefresh("Expense saved. Shares and balances are updated.");
  },"Add expense");
}
async function addMemberModal() {
  const group=state.group.id, users=await all("/users"), available=users.filter(u=>!state.members.some(m=>m.id===u.id));
  openModal("Add a person",`<label>Create a new person<input name="name" maxlength="100" placeholder="Their name"></label><p>Or choose an existing person below. A new name takes priority.</p><label>Existing person<select name="user_id"><option value="">Choose a person</option>${options(available)}</select></label>`,async form=>{
    let id=Number(form.get("user_id"));const name=form.get("name").trim();
    if(name)id=(await api("/users","POST",{name})).id;
    if(!id)throw new Error("Enter a new name or choose an existing person.");
    await api(`/groups/${group}/members/${id}`,"PUT");
    const updated=await api(`/groups/${group}`);state.groups=state.groups.map(g=>g.id===group ? updated : g);state.group=updated;renderGroups();$("#group-subtitle").textContent=`${updated.member_count} people · INR · ${updated.timezone}`;
    await saveAndRefresh("Person added. Older expense shares are unchanged.");
  },"Add person");
}
async function sampleTrip() {
  openModal("Try a fresh trip",`<p>Create a separate trip with Mohit, Rahul and Ankit, plus Dinner (₹1,200), Taxi (₹600) and Hotel (₹3,000). All figures you see will come from real saved API records.</p><label>Trip name<input name="name" maxlength="100" required value="Goa Trip · ${esc(new Date().toLocaleTimeString("en-IN",{hour:"2-digit",minute:"2-digit"}))}"></label><p>This leaves everyone else's trips untouched. If a request fails midway, already-created records remain; no shared data is deleted.</p>`,async form=>{
    const users=[];
    for(const name of ["Mohit","Rahul","Ankit"])users.push(await api("/users","POST",{name}));
    const group=await api("/groups","POST",{name:form.get("name"),timezone:"Asia/Kolkata"});
    for(const user of users)await api(`/groups/${group.id}/members/${user.id}`,"PUT");
    for(const [description,amount,payer] of [["Dinner","1200.00",0],["Taxi to beach","600.00",1],["Hotel stay","3000.00",0]])await api(`/groups/${group.id}/expenses`,"POST",{description,amount,paid_by:users[payer].id});
    $("#modal").close();setTab("overview",false);await loadGroups(group.id);notice("Your demo trip is ready. Try adding an expense, switching the personal view, or recording a settlement.");
  },"Create demo trip");
}
function setTab(tab, reload=true) {state.tab=tab;document.querySelectorAll("[data-tab]").forEach(b=>{b.classList.toggle("active",b.dataset.tab===tab);if(b.dataset.tab===tab)b.setAttribute("aria-current","page");else b.removeAttribute("aria-current");});if(reload)refresh();}
$("#modal-form").addEventListener("submit",async event=>{event.preventDefault();$("#save-modal").disabled=true;$("#cancel-modal").disabled=true;$("#close-modal").disabled=true;$("#form-error").textContent="";try{await modalSave(new FormData(event.currentTarget));}catch(error){$("#form-error").textContent=error.message;}finally{$("#save-modal").disabled=false;$("#cancel-modal").disabled=false;$("#close-modal").disabled=false;}});
$("#modal").addEventListener("cancel",event=>{if($("#save-modal").disabled)event.preventDefault();});
$("#close-modal").onclick=$("#cancel-modal").onclick=()=>$("#modal").close();
$("#add-expense").onclick=expenseModal;
$("#sample-trip").onclick=sampleTrip;
$("#new-group").onclick=()=>openModal("Create a trip",`<label>Trip name<input name="name" required maxlength="100" placeholder="e.g. Weekend in Jaipur"></label><label>Timezone<input name="timezone" required value="Asia/Kolkata" maxlength="64"></label><p>Add people in the People tab, then record your first expense.</p>`,async form=>{const group=await api("/groups","POST",{name:form.get("name"),timezone:form.get("timezone")});$("#modal").close();setTab("members",false);await loadGroups(group.id);notice("Trip created. Add your people to get started.");},"Create trip");
document.addEventListener("click",async event=>{
  const button=event.target.closest("button");if(!button)return;
  try {
    if(button.dataset.group){await selectGroup(Number(button.dataset.group));$("#search-results").hidden=true;}
    if(button.dataset.tab)setTab(button.dataset.tab);
    if(button.dataset.openTab)setTab(button.dataset.openTab);
    if(button.hasAttribute("data-refresh"))await refresh();
    if(button.hasAttribute("data-clear-dates")){state.reportFilters={};await refresh();}
    if(button.dataset.page){state[button.dataset.page==="expenses" ? "offset" : "historyOffset"]=Number(button.dataset.offset);await refresh();}
    if(button.id==="add-member")await addMemberModal();
    if(button.dataset.payFrom){const group=state.group.id,mode=state.mode;openModal("Record an external repayment",`<p>Only record this after the payer has paid outside the app. No money is transferred here.</p><label>Amount (INR)<input name="amount" type="number" min="0.01" step="0.01" max="${esc(button.dataset.payAmount)}" required value="${esc(button.dataset.payAmount)}"></label><label>Note<input name="note" maxlength="500" placeholder="e.g. Paid via UPI"></label><p>You can record a partial repayment. The server rechecks the latest balance before saving.</p>`,async form=>{await api(`/groups/${group}/settlements`,"POST",{from_user_id:Number(button.dataset.payFrom),to_user_id:Number(button.dataset.payTo),amount:form.get("amount"),mode,note:form.get("note")||null});await saveAndRefresh("Repayment recorded. Balances and suggestions are updated.");},"Record repayment");}
    if(button.dataset.detail){const expense=await api(`/groups/${state.group.id}/expenses/${button.dataset.detail}`);openModal(expense.description,`<p>${money(expense.amount)} paid by ${esc(expense.paid_by.name)} · ${esc(expense.split_type)} split</p>${expense.shares.map(s=>`<div class="person-row">${person(s.user.name)}<span class="person-name">${esc(s.user.name)}</span><span class="amount">${money(s.amount)}</span></div>`).join("")}<p>The payer's share is consumption, never a debt to themselves.</p>`,async()=>$("#modal").close(),"Done");}
    if(button.dataset.feature){setTab(button.dataset.feature);$("#search-results").hidden=true;}
  }catch(error){notice(error.message,true);}
});
document.addEventListener("change",async event=>{
  const target=event.target;
  if(target.id==="split-type"){$("#custom-splits").hidden=target.value!=="custom";return;}
  if(target.id==="view-user"){state.userId=Number(target.value);await refresh();}
  if(target.id==="settlement-mode"){state.mode=target.value;await refresh();}
  if(target.dataset.category){target.disabled=true;try{await api(`/groups/${state.group.id}/expenses/${target.dataset.category}/category`,"PATCH",{category:target.value});notice("Category corrected. Analytics will use your choice.");await refresh();}catch(error){notice(error.message,true);await refresh();}}
});
document.addEventListener("submit",async event=>{
  if(event.target.id==="expense-filter"){event.preventDefault();state.filters=Object.fromEntries([...new FormData(event.target)].filter(([,v])=>v));state.offset=0;await refresh();}
  if(event.target.id==="report-filter"){event.preventDefault();state.reportFilters=Object.fromEntries(new FormData(event.target));await refresh();}
});
$("#search").addEventListener("input",()=>{clearTimeout(searchTimer);const version=++searchVersion,q=$("#search").value.trim();if(!q){$("#search-results").hidden=true;return;}searchTimer=setTimeout(async()=>{try{const data=await api(`/search?q=${encodeURIComponent(q)}&limit=10`);if(version!==searchVersion)return;$("#search-results").innerHTML=data.items.map(hit=>{
    if(hit.type==="groups")return `<button class="search-hit" data-group="${Number(hit.id)}">${esc(hit.label)}<small>Trip</small></button>`;
    // Expense/user detail URLs are safe server-defined numeric paths; feature templates open the docs.
    const url=/^\/api\/v1\/(groups|users)\/\d+(\/expenses\/\d+)?$/.test(hit.api_path) ? hit.api_path : "/docs";
    return `<a class="search-hit" href="${esc(url)}" target="_blank" rel="noopener">${esc(hit.label)}<small>${esc(hit.type)} · View ${url==="/docs" ? "API documentation" : "API result"} ↗</small></a>`;
  }).join("")||empty("No results. Try ‘dinner’, ‘Goa’ or ‘analytics’.");$("#search-results").hidden=false;}catch(error){if(version===searchVersion){$("#search-results").innerHTML=empty(error.message);$("#search-results").hidden=false;}}},300);});
document.addEventListener("click",event=>{if(!event.target.closest(".search-wrap"))$("#search-results").hidden=true;});
$("#search").addEventListener("keydown",event=>{if(event.key==="Escape")$("#search-results").hidden=true;});
loadGroups().catch(error=>{notice(error.message,true);$("#workspace").innerHTML=empty("Could not reach the API. Wait for the service to wake up, then reload this page.");});
