const STORAGE_KEY = 'cendavo-demo-v1';
const STATUSES = ['New', 'Follow-up', 'Done'];
// Fictional tailor-shop sample requests. Dates are fixed, so "Date passed" on
// sample-2 is intentional: it shows the attention cue without any setup.
const seed = [
  {id:'sample-1',name:'Alex Morgan',service:'Alteration',date:'2026-10-14',note:'Hem two pairs of trousers',status:'New',created:'2026-10-10'},
  {id:'sample-2',name:'Sam Lee',service:'Repair',date:'2026-10-08',note:'Replace a broken zip on a winter coat',status:'Follow-up',created:'2026-10-05'},
  {id:'sample-3',name:'Jordan Reyes',service:'Alteration',date:'2026-10-25',note:'Fitting for a wedding guest dress',status:'New',created:'2026-10-09'},
  {id:'sample-4',name:'Casey Nguyen',service:'Alteration',date:'2026-10-03',note:'Shorten suit jacket sleeves',status:'Done',created:'2026-09-28'}
];
const EMPTY_DRAFT = 'Choose "Draft reply" on a request to prepare a draft.';
const isIsoDate = value => {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const d = new Date(value + 'T00:00:00Z');
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === value;
};
const cleanText = (value, max) => typeof value === 'string' ? value.trim().slice(0, max) : '';

// Stored data is untrusted (it can be edited in DevTools): keep only well-formed items.
function normaliseItems(raw) {
  if (!Array.isArray(raw)) return structuredClone(seed);
  const ids = new Set();
  const valid = [];
  for (const entry of raw) {
    if (!entry || typeof entry !== 'object') continue;
    const id = cleanText(entry.id, 80);
    const name = cleanText(entry.name, 80);
    const service = cleanText(entry.service, 40);
    if (!id || !name || !service || ids.has(id) || !STATUSES.includes(entry.status)) continue;
    ids.add(id);
    valid.push({id, name, service, date: isIsoDate(entry.date) ? entry.date : '', note: cleanText(entry.note, 500), status: entry.status, created: isIsoDate(entry.created) ? entry.created : ''});
  }
  return valid.length ? valid : structuredClone(seed);
}

function friendlyDate(value) {
  if (!isIsoDate(value)) return '';
  return new Date(value + 'T00:00:00Z').toLocaleDateString('en-AU', {weekday: 'short', day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'});
}

// Static clarifying question per service. Unknown services get none.
const SERVICE_CLAUSES = {
  Alteration: 'Could you send a photo of the item and tell us what change you need?',
  Cleaning: 'How many bedrooms and bathrooms does the property have?',
  Laundry: 'Roughly how many items or bags do you have, and are there any special care needs?',
  Repair: 'Could you send a photo of the damage and tell us what happened?',
  Other: 'Could you tell us a little more about what you need?'
};

function buildDraft(item) {
  if (!item || typeof item.name !== 'string' || typeof item.service !== 'string') return EMPTY_DRAFT;
  const when = friendlyDate(item.date);
  const timing = when ? `We can discuss your request for ${when}. Please let us know what time works for you.` : 'Please let us know what date and time work for you.';
  const clause = Object.hasOwn(SERVICE_CLAUSES, item.service) ? ` ${SERVICE_CLAUSES[item.service]}` : '';
  return `Hi ${item.name}, thanks for your ${item.service.toLowerCase()} enquiry. ${timing}${clause}\n\nThis is a draft only. Review it before sending.`;
}

const FILTERS = ['All', ...STATUSES];
const normaliseFilter = value => FILTERS.includes(value) ? value : 'All';

// Text cue for open requests whose preferred date is today or already past.
function attentionLabel(item, todayIso) {
  if (!item || item.status === 'Done' || !isIsoDate(item.date) || !isIsoDate(todayIso)) return '';
  if (item.date === todayIso) return 'Due today';
  return item.date < todayIso ? 'Date passed' : '';
}

// View-only: filtered copy, open items first, Done last, then earliest date (no date last).
function visibleItems(list, filter) {
  const active = normaliseFilter(filter);
  const rank = item => item.status === 'Done' ? 1 : 0;
  return (Array.isArray(list) ? list : [])
    .map((item, index) => ({item, index}))
    .filter(({item}) => active === 'All' || item.status === active)
    .sort((a, b) => rank(a.item) - rank(b.item)
      || (a.item.date || '9999-99-99').localeCompare(b.item.date || '9999-99-99')
      || a.index - b.index)
    .map(({item}) => item);
}

if (typeof module !== 'undefined') module.exports = {normaliseItems, buildDraft, friendlyDate, isIsoDate, attentionLabel, visibleItems, normaliseFilter, seed};

if (typeof document !== 'undefined') {
  const $ = selector => document.querySelector(selector);
  let items;
  try { items = normaliseItems(JSON.parse(localStorage.getItem(STORAGE_KEY))); }
  catch { items = structuredClone(seed); }
  let selectedId = null;
  const say = message => { $('#demo-status').textContent = message; };
  const localToday = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
  function save(){try{localStorage.setItem(STORAGE_KEY,JSON.stringify(items));return true;}catch{say('Browser storage is unavailable. Your changes will last only until this page closes.');return false;}}
  function textElement(tag,value){const node=document.createElement(tag);node.textContent=value;return node;}
  let filter='All';
  function render(focusId){
    const body=$('#requests');body.replaceChildren();
    const shown=visibleItems(items,filter);
    if(!shown.some(item=>item.id===selectedId))selectedId=null;
    const today=localToday();
    if(!shown.length){
      const tr=document.createElement('tr');const td=textElement('td',filter==='All'?'No requests yet. Add a sample request below.':`No ${filter} requests.`);
      td.colSpan=5;tr.append(td);body.append(tr);
    }
    for(const item of shown){
      const tr=document.createElement('tr');
      if(item.id===selectedId)tr.className='selected';
      [item.name,item.service,friendlyDate(item.date)||'Not set'].forEach(value=>tr.append(textElement('td',value)));
      const status=document.createElement('td');
      const pill=textElement('span',item.status);
      pill.className='pill'+(item.status==='New'?' open':item.status==='Done'?' done':'');
      status.append(pill);
      const attention=attentionLabel(item,today);
      if(attention){const cue=textElement('span',attention);cue.className='pill open';cue.style.marginLeft='.4rem';status.append(cue);}
      tr.append(status);
      const action=document.createElement('td');action.className='actions';
      const select=document.createElement('select');select.className='table-action';
      select.setAttribute('aria-label','Status for '+item.name);
      for(const option of STATUSES){const o=textElement('option',option);o.value=option;o.selected=option===item.status;select.append(o);}
      select.addEventListener('change',()=>{
        if(!STATUSES.includes(select.value))return;
        item.status=select.value;const stored=save();
        const hidden=filter!=='All'&&item.status!==filter;
        render(hidden?undefined:item.id);
        say(stored?`${item.name} marked ${item.status}.${hidden?` Hidden by the ${filter} filter.`:''}`:'Status changed, but browser storage is unavailable.');
      });
      const draftButton=textElement('button','Draft reply');draftButton.className='table-action';draftButton.type='button';
      draftButton.setAttribute('aria-pressed',String(item.id===selectedId));
      draftButton.addEventListener('click',()=>{selectedId=item.id;render();say(`Draft prepared for ${item.name}. Nothing was sent.`);});
      action.append(select,draftButton);tr.append(action);body.append(tr);
      if(item.id===focusId)select.focus();
    }
    $('#count-new').textContent=items.filter(item=>item.status==='New').length;
    $('#count-followup').textContent=items.filter(item=>item.status==='Follow-up').length;
    $('#count-total').textContent=items.length;
    const selected=items.find(item=>item.id===selectedId);
    $('#request-details').textContent=selected?`Request details from ${selected.name}: ${selected.note||'No details provided.'}`:'';
    $('#followup-draft').value=buildDraft(selected);
  }
  $('#status-filter').addEventListener('change',event=>{
    filter=normaliseFilter(event.target.value);event.target.value=filter;render();
    const count=visibleItems(items,filter).length;
    say(count?`Showing ${count} ${filter==='All'?'':filter+' '}request${count===1?'':'s'}.`:(filter==='All'?'No requests yet.':`No ${filter} requests.`));
  });
  const draftBox=$('#followup-draft');
  const detailsNode=document.createElement('p');detailsNode.id='request-details';detailsNode.className='note';
  draftBox.parentNode.insertBefore(detailsNode,draftBox);
  const dateInput=$('#request-form input[name="date"]');
  dateInput.min=localToday();
  $('#request-form').addEventListener('submit',event=>{
    event.preventDefault();const form=event.currentTarget;const data=new FormData(form);
    const date=String(data.get('date'));
    if(date&&date<localToday()){say('Choose a preferred date from today onwards.');return;}
    const service=cleanText(String(data.get('service')),40);
    const name=cleanText(String(data.get('name')),80);
    if(!name){say('Enter a name that is not blank.');return;}
    if(!service){say('Choose a service.');return;}
    if(date&&!isIsoDate(date)){say('Enter a valid preferred date.');return;}
    items.unshift({id:crypto.randomUUID(),name,service,date:isIsoDate(date)?date:'',note:cleanText(String(data.get('note')),500),status:'New',created:localToday()});
    const stored=save();render();form.reset();if(stored)say('Sample request added on this device.');
  });
  $('#reset-demo').addEventListener('click',()=>{items=structuredClone(seed);selectedId=null;filter='All';$('#status-filter').value='All';const stored=save();render();if(stored)say('Sample data restored.');});
  $('#copy-followup').addEventListener('click',async()=>{
    const draft=$('#followup-draft');
    if(!selectedId){say('Choose "Draft reply" on a request first.');return;}
    try{await navigator.clipboard.writeText(draft.value);say('Draft copied. Nothing was sent.');}
    catch{draft.focus();draft.select();say('Could not copy automatically. The draft is selected: copy it by hand.');}
  });
  render();
}
