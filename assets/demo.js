const STORAGE_KEY = 'cendavo-demo-v1';
const seed = [
  {id:'sample-1',name:'Alex Morgan',service:'Alteration',date:'2026-10-14',note:'Hem two pairs of trousers',status:'New',created:'2026-10-10'},
  {id:'sample-2',name:'Sam Lee',service:'Cleaning',date:'2026-10-16',note:'One bedroom apartment',status:'Follow-up',created:'2026-10-09'}
];
const $ = selector => document.querySelector(selector);
let items;
try { items = JSON.parse(localStorage.getItem(STORAGE_KEY)); if (!Array.isArray(items)) throw Error(); }
catch { items = structuredClone(seed); }
function save(){try{localStorage.setItem(STORAGE_KEY,JSON.stringify(items));return true;}catch{$('#demo-status').textContent='Browser storage is unavailable. Your changes will last only until this page closes.';return false;}}
function textElement(tag,value){const node=document.createElement(tag);node.textContent=value;return node;}
function render(){
  const body=$('#requests');body.replaceChildren();
  for(const item of items){
    const tr=document.createElement('tr');
    [item.name,item.service,item.date].forEach(value=>tr.append(textElement('td',value)));
    const status=document.createElement('td');const pill=textElement('span',item.status);pill.className='pill '+(item.status==='New'?'open':'');status.append(pill);tr.append(status);
    const action=document.createElement('td');const button=textElement('button',item.status==='New'?'Mark follow-up':'Mark done');button.className='table-action';button.type='button';button.addEventListener('click',()=>{item.status=item.status==='New'?'Follow-up':'Done';const stored=save();render();if(stored)$('#demo-status').textContent='Sample status updated.';});action.append(button);tr.append(action);body.append(tr);
  }
  if(!items.length){const tr=document.createElement('tr');const td=textElement('td','No requests yet. Add a sample request below.');td.colSpan=5;td.className='empty';tr.append(td);body.append(tr);}
  $('#count-new').textContent=items.filter(item=>item.status==='New').length;
  $('#count-followup').textContent=items.filter(item=>item.status==='Follow-up').length;
  $('#count-total').textContent=items.length;
  const selected=items.find(item=>item.status==='Follow-up'||item.status==='New');
  $('#followup-draft').value=selected ? `Hi ${selected.name}, thanks for your ${selected.service.toLowerCase()} enquiry. We can discuss your request for ${selected.date}. Please let us know what time works for you.\n\nThis is a draft only. Review it before sending.` : 'Move a request into follow-up to prepare a draft.';
}
$('#request-form').addEventListener('submit',event=>{
  event.preventDefault(); const data=new FormData(event.currentTarget);
  items.unshift({id:crypto.randomUUID(),name:String(data.get('name')).trim(),service:String(data.get('service')),date:String(data.get('date')),note:String(data.get('note')).trim(),status:'New',created:new Date().toISOString().slice(0,10)});
  const stored=save();render();event.currentTarget.reset();if(stored)$('#demo-status').textContent='Sample request added on this device.';
});
$('#reset-demo').addEventListener('click',()=>{items=structuredClone(seed);const stored=save();render();if(stored)$('#demo-status').textContent='Sample data restored.';});
$('#copy-followup').addEventListener('click',async()=>{await navigator.clipboard.writeText($('#followup-draft').value);$('#demo-status').textContent='Draft copied. Nothing was sent.';});
render();
