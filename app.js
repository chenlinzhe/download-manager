/* ---------- V1.5：应用内确认框 + 提示条（不再弹系统原生 MessageBox） ---------- */
let toastTimer=null;
function toast(message,isError){
 let t=el('toast');if(!t)return;
 let text=String(message==null?'':message);
 t.textContent=text;t.title='点击关闭';
 t.className='toast show'+(isError?' err':'');
 if(toastTimer)clearTimeout(toastTimer);
 toastTimer=setTimeout(()=>{t.className='toast'+(isError?' err':'')},Math.min(12000,4200+text.length*60));
}
function hijackAlert(){window.alert=message=>toast(message)}
hijackAlert();
window.addEventListener('pywebviewready',hijackAlert);
let confirmFinish=null;
function uiConfirm(text,okLabel,title){
 return new Promise(resolve=>{
  let m=el('confirmModal');
  if(!m)return resolve(window.confirm(text));
  if(confirmFinish)confirmFinish(false);
  el('confirmTitle').textContent=title||'请确认';
  el('confirmText').textContent=String(text==null?'':text);
  let ok=el('confirmOk'),cancel=el('confirmCancel');
  ok.textContent=okLabel||'确定';
  m.classList.add('open');
  const done=v=>{
   if(!confirmFinish)return;
   confirmFinish=null;
   m.classList.remove('open');
   document.removeEventListener('keydown',onKey,true);
   ok.onclick=cancel.onclick=m.onclick=null;
   resolve(v);
  };
  const onKey=ev=>{
   if(ev.key==='Enter'){ev.preventDefault();ev.stopPropagation();done(true)}
   else if(ev.key==='Escape'){ev.preventDefault();ev.stopPropagation();done(false)}
  };
  confirmFinish=done;
  ok.onclick=ev=>{ev.stopPropagation();done(true)};
  cancel.onclick=ev=>{ev.stopPropagation();done(false)};
  m.onclick=ev=>{if(ev.target===m)done(false)};
  document.addEventListener('keydown',onKey,true);
  setTimeout(()=>ok.focus(),30);
 });
}
let items=[],chosen=new Set(),scanGroups=[],activeGroup='download',scanInfo=null,naturalPaths=null,searchVersion=0,sortKey='',sortDir=1,lastDestination='',moveTargets=[];
const native=()=>window.desktop||window.pywebview?.api;const el=id=>document.getElementById(id);function fmt(n){if(!n)return'0 B';let u=['B','KB','MB','GB','TB'],i=Math.min(4,Math.floor(Math.log(n)/Math.log(1024)));return(n/1024**i).toFixed(i?1:0)+' '+u[i]}function esc(s){return String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}function cls(r){return (r==='建议保留'||r==='保留（手工）')?'keep':r==='待确认'?'review':'drop'}function fuzzy(text,q){text=(text||'').toLowerCase();q=(q||'').toLowerCase().trim();if(!q)return true;return text.includes(q)}const REC_ORDER={'保留（手工）':0,'建议保留':1,'待确认':2,'不用保住':3};
function sortVal(x,k){switch(k){case'name':return (x.displayName||x.name||'').toLowerCase();case'rec':return REC_ORDER[x.recommendation]===undefined?9:REC_ORDER[x.recommendation];case'score':return x.score||0;case'size':return x.size||0;case'modified':return x.modified||'';case'ai':return (!x.aiHidden&&x.aiDescription&&x.aiDescription.summary)?1:0;default:return 0}}
function setSort(k){if(sortKey===k)sortDir=-sortDir;else{sortKey=k;sortDir=(k==='name'||k==='rec'||k==='ai')?1:-1}document.querySelectorAll('th.sortable').forEach(th=>{th.classList.remove('asc','desc');if(th.dataset.sort===sortKey)th.classList.add(sortDir>0?'asc':'desc')});render()}
function visible(){let q=el('q').value,f=el('filter').value,r=el('root').value,onlyNew=el('onlyNew').checked;let v=items.filter(x=>(x.group||'download')===activeGroup&&(naturalPaths?naturalPaths.has(x.path):fuzzy([x.name,x.displayName,x.path,x.kind,(x.aiHidden?'':(x.aiDescription||{}).summary),x.note].join(' '),q))&&(!f||x.recommendation===f)&&(!r||x.root===r)&&(!onlyNew||x.isNew));if(sortKey)v.sort((m,n)=>{let p=sortVal(m,sortKey),q2=sortVal(n,sortKey);return(p<q2?-1:p>q2?1:0)*sortDir});return v}
const STOP=new Set(('的了着是在有和与及或也都就才又再还只但并而这那此其某个吗呢吧啊呀哦嗯哈嗦啦喰么之对从向给被把让到于为以用想找要搜查看请帮哪什该我你他她它咱俺种').split(''));['一个','一下','一种','一些','一类','一款','这个','那个','这些','那些','哪个','哪些','这种','那种','哪种','这么','那么','这样','那样','一点','有些','东西','里面','我们','你们','他们','她们','它们','咱们','自己','可以','想要','需要','应该','看看','点儿','有点儿','如何','为什么','a','an','the','of','for','is','are','it','to','and','or','this','that','these','those','want','find','get','with','my','me','one','we','you','they'].forEach(w=>STOP.add(w));
function cutTerms(q){q=(q||'').toLowerCase();let toks=q.match(/[a-z0-9]+|[\u4e00-\u9fff]+/g)||[];let out=[],seen=new Set();for(let t of toks){if(t&&!seen.has(t)){seen.add(t);out.push(t);}}let kept=out.filter(c=>!STOP.has(c));return kept.length?kept:out;}
/* ---------- 资源标签（tab）：第一项固定是内置的「下载包」，其余由用户自建 ---------- */
function groupItems(){return items.filter(x=>(x.group||'download')===activeGroup)}
function groupOf(gid){return scanGroups.find(g=>g.id===gid)||null}
function activeGroupName(){let g=groupOf(activeGroup);return g?g.name:'下载包'}
function renderTags(){
 let bar=el('tagBar');if(!bar)return;
 let list=scanGroups.length?scanGroups:[{id:'download',name:'下载包',roots:[],count:0,builtin:true}];
 bar.hidden=false;
 bar.innerHTML='<span class="tag-tabs">'+list.map(g=>{
  let on=g.id===activeGroup;
  let tips=(g.roots&&g.roots.length)?g.roots.join('\n'):'这个标签下还没有目录：在目录下拉里选「＋ 新增目录（可多选）…」把目录加进来';
  let edit=g.builtin?'':'<button type="button" class="tag-edit" data-gid="'+esc(g.id)+'" title="给这个标签改名">✎</button>';
  return '<span class="tag-wrap'+(on?' on':'')+'"><button type="button" class="tag-main" data-gid="'+esc(g.id)+'" title="'+esc(tips)+'"><span class="tag-name">'+esc(g.name)+'</span><span class="tag-n">'+(g.count||0)+' 项</span></button>'+edit+'</span>';
 }).join('')+'</span><button type="button" class="tag-add" title="新建一个标签（例如「我的项目」），功能跟「下载包」完全一样，只是目录由你自己加">＋ 新建标签</button>';
 bar.querySelectorAll('button.tag-main').forEach(b=>b.onclick=()=>switchGroup(b.dataset.gid));
 bar.querySelectorAll('button.tag-edit').forEach(b=>b.onclick=e=>{e.stopPropagation();renameGroup(b.dataset.gid)});
 let add=bar.querySelector('button.tag-add');if(add)add.onclick=()=>newGroup();
}
/* 标签们的外框：所有标签共用一个圆角框，新建与改名的输入框也放进去 */
function tagTabs(){let bar=el('tagBar');return bar?bar.querySelector('.tag-tabs'):null}
function renderScanBar(){
 let bar=el('scanBar');if(!bar||!scanInfo)return;
 let g=groupOf(activeGroup),roots=(g&&g.roots)||[],errs=scanInfo.errs||[];
 bar.textContent=(scanInfo.force?'已重新扫描 · ':'')+'「'+activeGroupName()+'」'+roots.length+' 个目录 · 更新于 '+String(scanInfo.generatedAt||'').replace('T',' ')+(scanInfo.reused?'（复用最近扫描结果，点“重新扫描”立即刷新）':'')+(errs.length?(' · '+errs.length+' 处读取失败（悬停查看）'):'');
 if(errs.length){bar.title=errs.slice(0,8).join('\n')+(errs.length>8?'\n…':'');bar.style.color='var(--warn-fg)'}
 else{bar.title='';bar.style.color=''}
}
function fillRootSelect(){
 let sel=el('root');if(!sel)return;
 let g=groupOf(activeGroup),roots=(g&&g.roots)||[],prev=sel.value;
 sel.innerHTML='<option value="__add__">＋ 新增目录（可多选）…</option><option value="">「'+esc(activeGroupName())+'」的全部目录</option>'+roots.map(x=>'<option value="'+esc(x)+'">'+esc(x)+'</option>').join('');
 sel.value=(prev&&roots.indexOf(prev)>=0)?prev:'';
}
function switchGroup(gid){
 if(!gid||gid===activeGroup)return;
 activeGroup=gid;chosen.clear();naturalPaths=null;
 if(el('q'))el('q').value='';
 fillRootSelect();renderTags();render();refreshCounts();renderScanBar();
 let g=groupOf(gid);
 if(enrichRunning>0)infoBusy(enrichLabel||infoBusyLabel||'AI 分析进行中…',true);else infoDone('已切到「'+(g?g.name:'下载包')+'」：'+(g?(g.count||0):0)+' 项，功能跟别的标签完全一样，只是看的是这一组目录',false);
}
async function groupCall(local,url,args,body){
 let api=native(),d;
 try{
  if(api&&typeof api[local]==='function')d=await api[local].apply(api,args);
  else d=await (await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
 }catch(e){d={ok:false,error:e.message}}
 return d||{ok:false,error:'没有返回结果'}
}
async function newGroup(){
 let bar=el('tagBar');if(!bar||bar.querySelector('.tag-input'))return;
 let ho=document.createElement('span');ho.className='tag-wrap editing';
 ho.innerHTML='<input class="tag-input" type="text" maxlength="12" placeholder="标签名，如：我的项目">';
 let box=tagTabs()||bar;
 box.appendChild(ho);
 let input=ho.querySelector('input');input.focus();
 let closed=false;
 async function finish(save){
  if(closed)return;closed=true;
  let text=save?input.value.trim():'';
  if(!text){renderTags();return}
  let d=await groupCall('add_group','/api/add_group',[text],{name:text});
  if(!d.ok){renderTags();return toast('新建标签失败：'+(d.error||'未知错误'),true)}
  let res=d.result||{};
  await load(false);
  if(res.id&&groupOf(res.id)){activeGroup=res.id;chosen.clear();naturalPaths=null;fillRootSelect();renderTags();render();refreshCounts();renderScanBar()}
  infoDone('已新建标签「'+(res.name||text)+'」，现在在目录下拉里选「＋ 新增目录（可多选）…」把目录加进来（按住 Ctrl / Shift 可一次选多个）',false);
 }
 input.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();finish(true)}else if(e.key==='Escape'){e.preventDefault();finish(false)}};
 input.onblur=()=>finish(true);
}
async function renameGroup(gid){
 let g=groupOf(gid);if(!g||g.builtin)return;
 let bar=el('tagBar');if(!bar||bar.querySelector('.tag-input'))return;
 let ho=null;
 bar.querySelectorAll('.tag-wrap').forEach(w=>{let b=w.querySelector('button.tag-main');if(b&&b.dataset.gid===gid)ho=w});
 if(!ho)return;
 ho.className='tag-wrap editing';
 ho.innerHTML='<input class="tag-input" type="text" maxlength="12" value="'+esc(g.name)+'">';
 let input=ho.querySelector('input');input.focus();input.select();
 let closed=false;
 async function finish(save){
  if(closed)return;closed=true;
  let text=save?input.value.trim():'';
  if(!text||text===g.name){renderTags();return}
  let d=await groupCall('rename_group','/api/rename_group',[gid,text],{id:gid,name:text});
  if(!d.ok){renderTags();return toast('改标签失败：'+(d.error||'未知错误'),true)}
  let old=g.name;
  for(const gg of scanGroups)if(gg.id===gid)gg.name=text;
  for(const x of items)if((x.group||'download')===gid)x.groupName=text;
  fillRootSelect();renderTags();render();refreshCounts();renderScanBar();
  infoDone('标签「'+old+'」已改名为「'+text+'」',false);
 }
 input.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();finish(true)}else if(e.key==='Escape'){e.preventDefault();finish(false)}};
 input.onblur=()=>finish(true);
}
/* V2.6：这一格只说一句话——你写的原样显示（不加任何标签），AI 说的前面标「AI：」 */
/* V2.8：这一格只有一种内容——你的。你一动手保存（改了 AI 那句、或整段留着接受它、或删掉它），
   格子里就只剩你的话，AI 那一行不再单独出现；只有你执意单独重做这一项时，才会在下面另起一行加回
   「AI：新结果」，你写的一个字都不动。 */
function aiBox(x){
	let a=x.aiDescription,sum=(a&&a.summary)?String(a.summary):'',note=String(x.note||'').trim();
	let showAI=!x.aiHidden&&sum;   /* 你动过的格子，AI 那句不再显示，也不会被扫描 / 批量分析写回来 */
	let when=(showAI&&a.searchedAt)?'<span class="ai-when" title="AI 这段说明生成于 '+esc(String(a.searchedAt).replace('T',' '))+(a.model?'（'+esc(a.model)+'）':'')+'">'+esc(whenAgo(a.searchedAt))+'</span>':'';
	let out='';
	if(note)out+='<div class="ai mine">'+esc(note)+'</div>';
	if(showAI)out+='<div class="ai"><b>AI：</b>'+esc(sum)+when+'</div>';
	if(out)return out;
	if(x.aiHidden)return '';   /* 你把这个格子删干净了：空着，AI 那句不会自己回来 */
	return '<span class="muted" title="还没有说明：勾选这一行后点工具栏的「AI 分析」，或者双击这一格自己写。">--</span>'
}
/* 说明这一格：双击（或按 Enter）才进编辑，单击不会进去；也可以用键盘 Tab 到这一格再按 Enter */
function noteCell(x){
	let title=x.aiHidden?'双击可以改这一格（这一格已经是你的话，AI 不再单独显示）；想让 AI 重新说一遍就按住 Shift 点「AI 分析」':'双击可以改这一格，或者按 Enter；单击不会进去';
	return '<td class="llm" tabindex="0" data-path="'+esc(x.path)+'" title="'+esc(title)+'">'+aiBox(x)+'</td>'
}
function render(){let v=visible();el('body').innerHTML=v.length?v.map(x=>'<tr data-path="'+esc(x.path)+'"><td><input class="pick" type="checkbox" data-id="'+esc(x.id)+'" '+(chosen.has(x.id)?'checked':'')+'></td><td><div class="name">'+esc(x.displayName||x.name)+(x.isNew?' <span class="new">新增</span>':'')+'</div><button class="path open-path" data-path="'+esc(x.parentPath||x.path)+'" title="打开包所在目录">所在目录：'+esc(x.parentPath||x.path)+'</button><div class="muted">'+esc(x.kind)+' · '+x.files+' 文件</div></td>'+noteCell(x)+'<td><span class="badge '+cls(x.recommendation)+'">'+x.recommendation+(x.manualKeep?'<button class="badge-x" data-unkeep="'+esc(x.path)+'" title="取消保留（按实际情况重新评估）">✕</button>':'')+'</span></td><td><b>'+x.score+'</b></td><td>'+fmt(x.size)+'</td><td>'+esc(x.modified.slice(0,10))+'<div class="muted">'+x.ageDays+' 天前</div></td><td>'+esc(x.redownload)+'</td><td class="'+(x.suspicious?'warn':'')+'">'+esc(x.registration)+'</td><td class="why">'+x.reasons.map(esc).join('；')+'</td></tr>').join(''):'<tr><td colspan="10" class="empty">没有符合筛选条件的项目</td></tr>';document.querySelectorAll('.open-path').forEach(e=>e.onclick=async()=>{let d=await native().open_path(e.dataset.path);if(!d.ok)alert(d.error)});document.querySelectorAll('button.badge-x').forEach(b=>b.onclick=e=>{e.stopPropagation();unkeepRows([b.dataset.unkeep])});document.querySelectorAll('td.llm').forEach(td=>{td.ondblclick=()=>editNote(td);td.onkeydown=e=>{if(e.target&&e.target.tagName==='TEXTAREA')return;if(e.key==='Enter'||e.key==='F2'){e.preventDefault();editNote(td)}}});document.querySelectorAll('.pick').forEach(e=>e.onchange=()=>{e.checked?chosen.add(e.dataset.id):chosen.delete(e.dataset.id);update()});update()}function selectedItems(){return items.filter(x=>chosen.has(x.id))}
function selectedPaths(){return selectedItems().map(x=>x.path)}
function update(){
 let n=chosen.size,picked=selectedItems();
 let anyKeep=picked.some(x=>x.manualKeep),anyUnkept=picked.some(x=>!x.manualKeep),kept=picked.filter(x=>x.manualKeep).length;
 el('selected').textContent='已选 '+n+' 项';
 let keep=el('keep'),unkeep=el('unkeep'),ignore=el('ignore'),move=el('move'),del=el('del');
 keep.disabled=!n||!anyUnkept;
 unkeep.disabled=!n||!anyKeep;
 ignore.disabled=!n;move.disabled=!n;del.disabled=!n;
 keep.title=!n?'先在左侧勾选项目，再点这里标为保留':(anyUnkept?('把勾选的 '+n+' 项标为保留：永久留用，不再出现在清理建议里'):'勾选的项目都已标为保留，不需要重复操作');
 unkeep.title=!n?'先在左侧勾选项目，再点这里取消保留':(anyKeep?('取消勾选项目里的 '+kept+' 项「保留」标记，取消后重新参与清理建议'):'勾选的项目都没有「保留」标记，不需要取消');
 ignore.title=!n?'先在左侧勾选项目，再点这里设为忽略':('把勾选的 '+n+' 项加入忽略名单：以后扫描直接跳过，不删除任何文件');
 move.title=!n?'先在左侧勾选项目，再点这里转移':('把勾选的 '+n+' 项转移到你选定的目录（不删除文件，同名不覆盖）');
 del.title=!n?'先在左侧勾选项目，再点这里移到回收站':('把勾选的 '+n+' 项移到 Windows 回收站（还能从回收站还原）');
}
async function load(force){
 infoBusy(force?'正在重新扫描全部目录…':'正在加载扫描结果…');
 el('scanBar').textContent=force?'正在全盘重新扫描…':'正在加载扫描结果…';el('scanBar').title='';el('scanBar').style.color='';
 let rs=el('rescan');if(rs){rs.disabled=true;rs.textContent='扫描中…'}
 let api=native(),timer=null;
 if(api&&typeof api.scan_status==='function'){timer=setInterval(async()=>{try{let s=await api.scan_status();if(s&&s.phase)el('scanBar').textContent=s.total?('正在'+s.phase+' '+s.done+' / '+s.total+'，请稍候…'):('正在'+s.phase+'…')}catch(_){}},400)}
 try{
  let d=api?await api.scan(!!force):await (await fetch('/api/scan'+(force?'?force=1':''))).json();
  if(d.error)throw Error(d.error);
  items=d.items;chosen.clear();
  scanGroups=(d.groups||[]).slice();
  if(!scanGroups.length)scanGroups=[{id:'download',name:'下载包',roots:d.roots||[],count:items.length,builtin:true}];
  if(!groupOf(activeGroup))activeGroup=scanGroups[0].id;
  scanInfo={generatedAt:d.generatedAt,force:!!force,reused:!!d.reused,errs:d.errors||[]};
  refreshCounts();
  fillRootSelect();
  renderScanBar();
  render();
  renderTags();
  infoDone((force?'重新扫描完成：「':'扫描完成：「')+activeGroupName()+'」'+groupItems().length+' 项'+(d.reused?'（复用最近扫描结果）':''),false);
  if(api){
   let cfg=await api.get_settings();
   applySettingsState(cfg&&cfg.ok?cfg.result:null);
   if(cfg&&cfg.ok&&cfg.result&&cfg.result.destination)lastDestination=cfg.result.destination;
   let missing=items.filter(x=>!x.aiDescription&&!String(x.note||'').trim()&&(force?x.isNew:true)).map(x=>x.path);
   if(cfg&&cfg.ok&&cfg.result.autoAnalyze&&cfg.result.apiKeyMasked&&missing.length)enrich(missing,true)
  }
 }catch(e){
  el('scanBar').textContent='加载失败';el('body').innerHTML='<tr><td colspan="10" class="empty">'+esc(e.message)+'</td></tr>'
 }finally{if(timer)clearInterval(timer);if(rs){rs.disabled=false;rs.textContent='重新扫描'}}
}

async function postAction(url,payload){
 if(native()){let d;if(url==='/api/move')d=await native().move(payload.paths,payload.destination);else if(url==='/api/keep')d=await native().keep(payload.paths);else d=await native().recycle(payload.paths);if(!d.ok)throw Error(d.error);return d}
 let r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),cache:'no-store'}),text=await r.text(),d=JSON.parse(text);if(!r.ok||!d.ok)throw Error(d.error||('HTTP '+r.status));return d
}


/* ---------- V1.8：工具栏左侧的信息条 ---------- */
/* 凡是「现在要告诉用户的事」都显示在这里：AI 分析进度、扫描与整理结果等；按钮固定在右侧。 */
let infoHideTimer = null, infoTickTimer = null, infoStart = 0, infoBusyLabel = '', busyActive = false, enrichRunning = 0, enrichLabel = '';
function infoShow(text, kind) {
	let s = el('infoBar');
	if (!s) return;
	if (infoHideTimer) { clearTimeout(infoHideTimer); infoHideTimer = null }
	if (kind !== 'busy' && infoTickTimer) { clearInterval(infoTickTimer); infoTickTimer = null }
	s.className = 'info-bar show' + (kind && kind !== 'plain' ? ' ' + kind : '');
	s.textContent = String(text == null ? '' : text)
}
function infoBusy(text, resume) {
	if (!resume) infoStart = Date.now();
	busyActive = true; infoBusyLabel = String(text || '');
	infoShow(infoBusyLabel, 'busy');
	if (infoTickTimer) clearInterval(infoTickTimer);
	infoTickTimer = setInterval(() => {
		let s = el('infoBar');
		if (!s || !s.classList.contains('busy')) return;
		s.textContent = infoBusyLabel + ' · 已用 ' + Math.round((Date.now() - infoStart) / 1000) + ' 秒'
	}, 1000)
}
function infoBusyText(text) {
	infoBusyLabel = String(text || '');
	let s = el('infoBar');
	if (s && s.classList.contains('busy')) s.textContent = infoBusyLabel + ' · 已用 ' + Math.round((Date.now() - infoStart) / 1000) + ' 秒'
}
function infoHideLater(ms) {
	if (infoHideTimer) clearTimeout(infoHideTimer);
	infoHideTimer = setTimeout(() => {
		infoHideTimer = null;
		if (infoTickTimer) { clearInterval(infoTickTimer); infoTickTimer = null }
		let s = el('infoBar');
		if (s) { s.className = 'info-bar'; s.textContent = '' }
	}, ms == null ? 6000 : ms)
}
function infoDone(text, isErr) {
	busyActive = false; infoShow(text, isErr ? 'err' : 'done');
	infoHideLater(isErr ? 9000 : 6000)
}
/* ---------- V2.2：标题栏「自动问答」+ 顶部提示条开关 ---------- */
let llmReady = false, hideNotice = false;
function syncNotice() { let n = el('notice'); if (n) n.hidden = !!hideNotice }
function syncQa() {
	let q = el('qa'); if (!q) return;
	if (llmReady) {
		q.classList.remove('qa-locked');
		q.title = '功能问答：问一句软件怎么用的问题，按 Enter 出答案（会把功能说明 + README 全文发给 DeepSeek）；想按关键词过滤表格就打到下面的搜索框';
		q.placeholder = '自动问答：问一句怎么用，Enter 出答案'
	} else {
		q.classList.add('qa-locked');
		q.title = '要使用自动问答，请先到「设置」中配置 LLM KEY';
		q.placeholder = '自动问答（还没配置 LLM KEY）'
	}
}
/* ---------- V2.3：功能问答（功能说明 + README 全文直传，不建索引） ---------- */
let kbBusy = false, kbInfo = null;
function kbMetaBase() {
	if (!llmReady) return '还没配置 LLM KEY：配好之后这里可以直接问功能问题（比如「怎么把包永久保留」）';
	let s = '知识库＝这一页功能说明 + README 全文，每次提问整份发过去，不建索引、装了就能用';
	if (kbInfo && kbInfo.chars) s += '（约 ' + (kbInfo.chars / 10000).toFixed(1) + ' 万字' + (kbInfo.tokens ? ' / 约 ' + kbInfo.tokens + ' tokens' : '') + '）';
	return s
}
function syncKb() {
	let q = el('kbQ'); if (!q) return;
	if (llmReady) {
		q.classList.remove('kb-locked');
		q.title = '功能问答：问一句关于这个软件怎么用的问题，按 Enter 提交（会把功能说明全文发给 DeepSeek）';
		q.placeholder = '问一句：比如「怎么把某个包永久保留？」'
	} else {
		q.classList.add('kb-locked');
		q.title = '要使用功能问答，请先到「设置 → 模型设置」中配置 LLM KEY';
		q.placeholder = '功能问答（还没配置 LLM KEY）'
	}
	if (el('kbAsk')) el('kbAsk').disabled = kbBusy;
	if (el('kbMeta')) el('kbMeta').textContent = kbMetaBase()
}
async function loadKbInfo() {
	let api = native();
	if (!api || typeof api.kb_info !== 'function') return;
	try { let d = await api.kb_info(); if (d && d.ok) { kbInfo = d.result || null; syncKb() } } catch (_) { }
}
async function askKb() {
	if (kbBusy) return;
	let api = native(), q = el('kbQ'), box = el('kbA'), btn = el('kbAsk');
	if (!api || typeof api.ask_help !== 'function') { toast('功能问答仅桌面版可用', true); return }
	if (!llmReady) {
		if (box) { box.hidden = false; box.className = 'kb-answer err'; box.textContent = '要使用功能问答，请先到「设置 → 模型设置」中配置 LLM KEY'; }
		toast('要使用功能问答，请先到「设置 → 模型设置」中配置 LLM KEY', true);
		return
	}
	let text = (q.value || '').trim();
	if (!text) { toast('先输入想问的问题，例如「怎么把某个包永久保留」'); q.focus(); return }
	kbBusy = true; if (btn) { btn.disabled = true; btn.textContent = '回答中…' }
	if (box) { box.hidden = false; box.className = 'kb-answer'; box.textContent = '正在把功能说明全文发给 DeepSeek…'; }
	if (el('kbMeta')) el('kbMeta').textContent = '功能说明全文约 ' + (kbInfo && kbInfo.chars ? (kbInfo.chars / 10000).toFixed(1) + ' 万字' : '一万多字') + '，正在请求 DeepSeek…';
	let d;
	try { d = await api.ask_help(text) } catch (e) { d = { ok: false, error: (e && e.message) ? e.message : String(e) } }
	kbBusy = false; if (btn) { btn.disabled = false; btn.textContent = '提问' }
	if (!d || !d.ok) {
		if (box) { box.className = 'kb-answer err'; box.textContent = '没能回答：' + ((d && d.error) || '未知错误') }
		if (el('kbMeta')) el('kbMeta').textContent = kbMetaBase();
		return
	}
	let r = d.result || {};
	if (box) { box.className = 'kb-answer'; box.textContent = r.answer || '（模型没有给出内容）' }
	if (el('kbMeta')) el('kbMeta').textContent = kbMetaLine(r)
}
function kbMetaLine(r) {
	let u = (r && r.usage) || {}, bits = [];
	if (r && r.model) bits.push('模型 ' + r.model);
	if (u.prompt) bits.push('送入 ' + u.prompt + ' tokens' + (u.cached ? '（缓存命中 ' + u.cached + '）' : ''));
	if (u.completion) bits.push('回答 ' + u.completion + ' tokens');
	if (r && r.latencyMs) bits.push((r.latencyMs / 1000).toFixed(1) + ' 秒');
	if (r && r.kb && r.kb.tokens) bits.push('知识库约 ' + r.kb.tokens + ' tokens');
	return bits.join(' · ')
}
/* ---------- V2.4：标题栏「自动问答」直接出答案（以前它会把这句当成搜索词） ---------- */
let askBusy = false, askQuestion = '';
function askModalOpen(on) { let m = el('askModal'); if (m) m.classList.toggle('open', !!on) }
async function askFromHeader(text) {
	let api = native(), box = el('askA'), meta = el('askKbMeta');
	if (!api || typeof api.ask_help !== 'function') { toast('功能问答仅桌面版可用', true); return }
	if (askBusy) { toast('上一条还在回答，稍等一下'); return }
	askQuestion = text;
	if (el('askQ')) el('askQ').textContent = '问：' + text;
	if (box) { box.hidden = false; box.className = 'kb-answer'; box.textContent = '正在把功能说明全文发给 DeepSeek…' }
	if (meta) meta.textContent = kbMetaBase();
	if (el('askSearch')) el('askSearch').disabled = true;
	askModalOpen(true);
	askBusy = true;
	let d;
	try { d = await api.ask_help(text) } catch (e) { d = { ok: false, error: (e && e.message) ? e.message : String(e) } }
	askBusy = false;
	if (el('askSearch')) el('askSearch').disabled = false;
	if (!d || !d.ok) {
		if (box) { box.className = 'kb-answer err'; box.textContent = '没能回答：' + ((d && d.error) || '未知错误') }
		return
	}
	let r = d.result || {};
	if (box) { box.className = 'kb-answer'; box.textContent = r.answer || '（模型没有给出内容）' }
	if (meta) meta.textContent = kbMetaLine(r)
}
/* V2.4：环境变量里的 Key 被改坏时，用配置文件里的 DPAPI 备份恢复 */
async function restoreKeyBackup() {
	let api = native();
	if (!api || typeof api.restore_key_backup !== 'function') { toast('仅桌面版可用', true); return }
	try {
		let d = await api.restore_key_backup();
		if (!d || !d.ok) throw Error((d && d.error) || '恢复失败');
		let c = d.result || {};
		applySettingsState(c);
		if (typeof loadModels === 'function') await loadModels();
		toast('已用本机备份恢复 Key（尾号 ' + String(c.apiKeyMasked || '').slice(-4) + '），AI 分析可以用了');
	} catch (e) { toast('恢复失败：' + ((e && e.message) || e), true) }
}
function applySettingsState(c) {
	if (!c) return;
	llmReady = !!c.apiKeyMasked;
	hideNotice = !!c.hideNotice;
	if (el('showNotice')) el('showNotice').checked = !hideNotice;
	if (el('restoreKey')) el('restoreKey').hidden = !c.keyBackup;
	syncQa(); syncNotice(); syncKb()
}
function qaSubmit() {
	let q = el('qa'); if (!q) return;
	let text = q.value.trim();
	if (!llmReady) {
		toast('要使用自动问答，请先到「设置」中配置 LLM KEY', true);
		infoDone('要使用自动问答，请先到「设置」中配置 LLM KEY（设置 → 模型设置里填好 Key 并保存）', true);
		return
	}
	if (!text) { toast('先输入一句想知道的，例如「怎么把某个包永久保留」'); q.focus(); return }
	q.value = '';
	askFromHeader(text)
}
/* 老行为保留：把这句当成关键词交给「智能搜索」去过滤表格（问答框里点「用这句搜表格」走这里） */
function qaSearch(text) {
	let m = el('askModal'); if (m) m.classList.remove('open');
	if (!text) return;
	el('q').value = text; el('searchStatus').textContent = '';
	searchVersion++; naturalPaths = null;
	smartSearch()
}
function pad2(n) { return (n < 10 ? '0' : '') + n }
function stampOf(iso) {
	let t = Date.parse(String(iso || '').replace(' ', 'T'));
	return t > 0 ? t : 0
}
function agoFrom(ms) {
	if (!ms) return '';
	let s = Math.max(0, Math.round((Date.now() - ms) / 1000));
	if (s < 45) return '刚刚';
	if (s < 3600) return Math.max(1, Math.round(s / 60)) + ' 分钟前';
	if (s < 86400) return Math.round(s / 3600) + ' 小时前';
	if (s < 2592000) return Math.round(s / 86400) + ' 天前';
	let d = new Date(ms);
	return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate())
}
function whenAgo(iso) { return agoFrom(stampOf(iso)) }
/* 一组项目的「上次分析」：时间接近就只说一次，否则给出最近一次与最早一次 */
function analyzedAgo(list) {
	let stamps = (list || []).map(x => stampOf((x.aiDescription || {}).searchedAt)).filter(t => t > 0);
	if (!stamps.length) return '';
	let recent = Math.max.apply(null, stamps), oldest = Math.min.apply(null, stamps);
	if (recent - oldest < 120000) return agoFrom(recent);
	return '最近一次 ' + agoFrom(recent) + '（最早 ' + agoFrom(oldest) + '）'
}
async function enrich(paths, quiet = false, force = false, skipped = 0, deep = false) {
	if (!native() || !paths.length) return;
	let errors = [], b = el('aiAnalyze');
	if (b) b.disabled = true;
	enrichRunning++; infoBusy('正在分析 ' + paths.length + ' 项…');
	for (let i = 0; i < paths.length; i += 10) {
		let group = paths.slice(i, i + 10);
		let span = (i + 1) + '–' + Math.min(i + group.length, paths.length);
		enrichLabel = '正在分析第 ' + span + ' 项（共 ' + paths.length + ' 项）'; infoBusyText(enrichLabel);
		el('status').textContent = 'DeepSeek 并发分析 ' + span + ' / ' + paths.length;
		let d;
			try { d = await native().enrich(group, !!force, !!deep) } catch (e) { d = { ok: false, error: e.message } }
		if (d && d.result) for (let x of items) if (d.result[x.path]) x.aiDescription = d.result[x.path];
		if (d && d.fresh) for (let x of items) if (d.fresh.indexOf(x.path) >= 0) x.aiHidden = false;   /* 重做成功：AI 那句回到你写的话下面 */
		if (!editingPath) render(); else deferredRender = true;   /* 你正在改这一格就先不重绘，改完再画 */
		if (!d || !d.ok) errors.push(...Object.values((d && d.errors) || { error: (d && d.error) || '未知错误' }))
	}
	if (!editingPath) render(); else deferredRender = true;
	enrichRunning--;
	let ok = !errors.length;
	let tail = skipped ? ('（另 ' + skipped + ' 项已跳过）') : '';
	el('status').textContent = ok ? ('DeepSeek 分析完成并已缓存' + (skipped ? ' · 跳过 ' + skipped + ' 项' : '')) : ('分析完成，失败 ' + errors.length + ' 项（可选择后重试）');
	if (b) b.disabled = false;
	infoDone(ok ? ('AI 分析完成（' + paths.length + ' 项）' + tail) : ('分析完成，失败 ' + errors.length + ' 项，可勾选后重试'), !ok);
	if (!ok && !quiet) alert('AI 搜索失败：' + errors.join('；'))
}
async function smartSearch(){
 let q=el('q').value.trim(),version=++searchVersion,button=el('smartSearch'),message=el('searchStatus');
 if(!q){naturalPaths=null;message.textContent='请输入搜索内容';render();return}
 button.disabled=true;button.classList.add('searching');button.textContent='搜索中…';message.textContent='正在匹配关键词…';el('status').textContent='正在按关键词匹配…';
 await new Promise(resolve=>setTimeout(resolve,0));
 let qterms=cutTerms(q);
 let preApi=native();
 if(preApi&&typeof preApi.tokenize==='function'){try{let t=await preApi.tokenize(q);if(t&&t.ok&&Array.isArray(t.result)&&t.result.length)qterms=t.result}catch(_){}}
 let local=items.filter(x=>{let t=[x.name,x.displayName,x.path,x.kind,(x.aiHidden?'':(x.aiDescription||{}).summary),x.note].join(' ').toLowerCase();return qterms.some(w=>t.includes(w));}).map(x=>x.path);
 naturalPaths=new Set(local);render();
 try{
  let api=native();if(!api||typeof api.natural_search!=='function')throw Error('智能搜索接口尚未就绪');
  message.textContent='已按关键词匹配 '+local.length+' 项，正在用 AI 扩展语义…';el('status').textContent='DeepSeek 正在理解搜索条件…';
  let timeout=new Promise((_,reject)=>setTimeout(()=>reject(Error('AI 语义搜索超时，关键词结果已保留')),60000));
  let d=await Promise.race([api.natural_search(q),timeout]);
  if(version!==searchVersion||el('q').value.trim()!==q)return;
  if(!d||!d.ok)throw Error((d&&d.error)||'没有返回结果');
  naturalPaths=new Set([...new Set([...local,...(d.result.paths||[])])]);
  message.textContent='找到 '+naturalPaths.size+' 项（关键词 + AI 语义）';el('status').textContent='智能搜索完成：关键词 + AI 语义';render();
 }catch(e){
  if(version!==searchVersion)return;
  message.textContent='已按关键词匹配 '+local.length+' 项（AI 语义不可用：'+e.message+'）';el('status').textContent='关键词搜索完成';
 }finally{
  if(version===searchVersion){button.disabled=false;button.classList.remove('searching');button.textContent='智能搜索';render()}
 }
}async function addRoot(){
 let d=await native().add_manual_root(activeGroup);
 if(d.cancelled)return;
 if(!d.ok)return alert(d.error);
 let r=d.result||{},added=r.added||[],skipped=r.skipped||[],failed=r.failed||[];
 if(!added.length&&!skipped.length&&!failed.length)return;
 let msg='';
 if(added.length===1)msg='已把目录加进「'+activeGroupName()+'」：'+added[0];
 else if(added.length>1)msg='已把 '+added.length+' 个目录加进「'+activeGroupName()+'」：'+added.slice(0,3).join('、')+(added.length>3?' 等 '+added.length+' 个':'');
 if(skipped.length)msg+=(msg?'；':'')+'跳过 '+skipped.length+' 个（'+skipped.slice(0,2).map(x=>x.reason||'').join('、')+'）';
 if(failed.length)msg+=(msg?'；':'')+failed.length+' 个没加成（'+failed.slice(0,2).map(x=>x.reason||x.error||'').join('、')+'）';
 infoBusy(msg+'，正在扫描新目录…');
 await load(true);
 infoDone(msg+'；扫描完成：「'+activeGroupName()+'」'+groupItems().length+' 项',failed.length>0)
}
let settingsPane='model';
async function openSettings(pane){
 el('settingsModal').classList.add('open');
 switchSettingsPane(pane||settingsPane||'model');
 loadSettingsState();
 loadModels()
}
/* 只读地把自动分析 / AI 判断目录 / 提示条这几个开关读进来——打开设置、刷新都不会写盘 */
async function loadSettingsState(){
 let api=native();
 if(!api||typeof api.get_settings!=='function'){ setModelStatus('设置仅桌面版可修改','err'); return }
 let d;try{d=await api.get_settings()}catch(e){d={ok:false,error:e.message}}
 if(!d||!d.ok)return toast('读取设置失败：'+((d&&d.error)||'未知错误'),true);
 let c=d.result||{};
 if(el('autoAnalyze'))el('autoAnalyze').checked=!!c.autoAnalyze;
 if(el('scanAI'))el('scanAI').checked=!!c.scanAI;
 if(el('showNotice'))el('showNotice').checked=!c.hideNotice;
 applySettingsState(c)
}
/* 「保存这两个开关」：只写这两个开关，不动任何模型配置，也不联网 */
async function saveSettingsOptions(){
 let api=native();
 if(!api||typeof api.save_settings!=='function')return toast('设置仅桌面版可修改',true);
 let d;try{d=await api.save_settings({autoAnalyze:el('autoAnalyze').checked,scanAI:el('scanAI').checked})}catch(e){d={ok:false,error:e.message}}
 if(!d||!d.ok)return toast('保存失败：'+((d&&d.error)||'未知错误'),true);
 toast('两个开关已保存（模型配置没动）')
}
function switchSettingsPane(pane){
 settingsPane=(pane==='ignore'||pane==='theme'||pane==='guide')?pane:'model';
 document.querySelectorAll('.settings-nav .nav-item').forEach(b=>b.classList.toggle('active',b.dataset.pane===settingsPane));
 document.querySelectorAll('.settings-body .pane').forEach(p=>{p.hidden=(p.dataset.pane!==settingsPane)});
 if(settingsPane==='ignore')loadIgnorePane();
 else if(settingsPane==='theme')syncThemeButtons();
 else if(settingsPane==='guide'){loadKbInfo();syncKb()}
 else if(settingsPane==='model')loadModels()
}
/* 立即 AI 分析：直接用当前默认模型跑，绝不顺手把界面上的东西存下来 */
async function analyzeNow(){
 if(!native())return alert('AI 分析仅桌面版可用');
 let cfg=await native().get_settings();
 if(!cfg.ok)return alert(cfg.error);
 if(!cfg.result.apiKeyMasked)return alert('当前默认模型还没有可用的 Key：请到「设置 → 模型设置」给默认模型填好 Key，再点「保存」或「设置为默认」。');
 if(cfg.result.keyFormatProblem)return alert('⚠️ '+cfg.result.keyFormatProblem+'\n\n请确认默认模型用的这把 Key（形如 sk- 开头共 35 位）后再点「立即 AI 分析」。');
 let missing=groupItems().filter(x=>!x.aiDescription&&!String(x.note||'').trim()).map(x=>x.path);
 if(!missing.length){let done=items.filter(x=>x.aiDescription&&x.aiDescription.searchedAt);return alert('所有项目都已有 AI 说明'+(done.length?'（'+analyzedAgo(done)+'分析过）':'')+'，不用再分析。\n想重做的话，回到表格勾选项目后按住 Shift 点工具栏的「AI 分析」。')}
 el('settingsModal').classList.remove('open');toast('开始 AI 分析 '+missing.length+' 个项目，完成后会提示');await enrich(missing,false)
}

async function action(type){
 let picked=selectedItems(),paths=picked.map(x=>x.path);
 if(!paths.length)return toast('请先在左侧勾选项目。');
 if(type==='keep'){
  if(!picked.some(x=>!x.manualKeep))return toast('勾选的项目都已标为保留，不需要重复操作。');
  if(!await uiConfirm('确认将所选 '+paths.length+' 项标为「保留」？\n保留＝永久留用，不受清理建议影响，重新扫描也不会覆盖；想撤销点徽章旁的 ✕，或选中后点工具栏的「取消保留」。','标为保留'))return;
  let btn=el('keep');btn.disabled=true;
  try{
   await postAction('/api/keep',{paths:paths});
   let want=new Set(paths.map(p=>String(p).toLowerCase()));
   for(let x of items)if(want.has(String(x.path).toLowerCase())){x.recommendation='保留（手工）';x.score=100;x.manualKeep=true;x.reasons=['你刚标记为保留；重新扫描不会覆盖']}
   render();refreshCounts();
   el('status').textContent='已标为保留 '+paths.length+' 项';
   infoDone('已标为保留 '+paths.length+' 项',false);
   toast('已标为保留 '+paths.length+' 项，重新扫描也不会覆盖。');
  }catch(e){toast('操作失败：'+e.message,true)}
  finally{update()}
  return;
 }
 if(!await uiConfirm('确认把所选 '+paths.length+' 项移到 Windows 回收站？\n还能从回收站还原。','移到回收站'))return;
 let btnDel=el('del');btnDel.disabled=true;
 try{
  let d=await postAction('/api/recycle',{paths:paths});
  let done=Array.isArray(d.result)?d.result:paths;
  dropItems(new Set(done.map(p=>String(p).toLowerCase())));
  refreshCounts();
  el('status').textContent='已移到回收站 '+done.length+' 项';
   infoDone('已移到回收站 '+done.length+' 项（可从回收站还原）',false);
  toast('已移到回收站 '+done.length+' 项（可从回收站还原）');
 }catch(e){toast('操作失败：'+e.message,true)}
 finally{update()}
}
document.querySelectorAll('th.sortable').forEach(th=>th.onclick=()=>setSort(th.dataset.sort));el('settingsBtn').onclick=()=>openSettings(settingsPane||'model');el('smartSearch').onclick=smartSearch;el('settingsAnalyze').onclick=analyzeNow;el('q').oninput=()=>{searchVersion++;naturalPaths=null;el('searchStatus').textContent='';el('smartSearch').disabled=false;el('smartSearch').classList.remove('searching');el('smartSearch').textContent='智能搜索';render()};el('q').onkeydown=e=>{if(e.key==='Enter')smartSearch()};el('filter').onchange=render;el('onlyNew').onchange=render;el('root').onchange=()=>{if(el('root').value==='__add__'){el('root').value='';addRoot()}else render()};el('rescan').onclick=()=>load(true);el('keep').onclick=()=>action('keep');el('move').onclick=()=>openMoveDialog(selectedPaths());el('del').onclick=()=>action('delete');el('all').onchange=e=>{visible().forEach(x=>e.target.checked?chosen.add(x.id):chosen.delete(x.id));render()};
el('noticeClose').onclick=async()=>{
	hideNotice=true;syncNotice();
	if(el('showNotice'))el('showNotice').checked=false;
	let api=native(),saved=false;
	if(api&&typeof api.save_settings==='function'){try{let d=await api.save_settings({hideNotice:true});saved=!!(d&&d.ok)}catch(_){}}
	toast(saved?'已关闭这条提示，之后不再自动显示；想恢复：设置 → 外观与主题 → 勾「启动时显示顶部提示条」':'已关闭这条提示（本次有效）')
};
el('showNotice').onchange=()=>{hideNotice=!el('showNotice').checked;syncNotice()};
el('qa').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();qaSubmit()}else if(e.key==='Escape'){e.preventDefault();el('qa').value='';el('qa').blur()}};
el('qa').onfocus=()=>{if(!llmReady)toast('要使用自动问答，请先到「设置」中配置 LLM KEY',true)};
el('kbAsk').onclick=askKb;
el('askClose').onclick=()=>askModalOpen(false);
el('askAgain').onclick=()=>{askModalOpen(false);if(el('qa'))el('qa').focus()};
el('askSearch').onclick=()=>qaSearch((askQuestion||'').trim());
el('askModal').onclick=e=>{if(e.target===el('askModal'))askModalOpen(false)};
if(el('restoreKey'))el('restoreKey').onclick=restoreKeyBackup;
el('kbQ').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();askKb()}else if(e.key==='Escape'){e.preventDefault();el('kbQ').value='';el('kbQ').blur()}};
el('kbQ').onfocus=()=>{if(!llmReady)toast('要使用功能问答，请先到「设置 → 模型设置」中配置 LLM KEY',true)};
syncKb();
syncQa();
let started=false;async function startWhenReady(){if(started)return;let api=native();if(api&&typeof api.scan==='function'&&typeof api.enrich==='function'){started=true;el('status').textContent='原生接口已连接';try{let v=await api.app_version();if(v&&v.ok&&v.result)el('ver').textContent='V'+v.result}catch(_){}try{let gl=await api.group_list();if(gl&&gl.ok&&Array.isArray(gl.result)&&gl.result.length){scanGroups=gl.result.slice();if(!groupOf(activeGroup))activeGroup=scanGroups[0].id;renderTags();fillRootSelect();refreshCounts()}}catch(_){}await load(false);return}el('status').textContent='正在连接本机分析接口…';setTimeout(startWhenReady,200)}window.addEventListener('pywebviewready',startWhenReady);startWhenReady();

/* V2.8：双击（或按 Enter）才进编辑。框里是你的话 + 下一行「AI：…」（那行是给你看的素材）：
   你留着它保存＝接受它的内容，保存时并入你自己的话，格子里不再有单独的 AI 那一行；
   你删掉它＝不要那部分；全删干净＝这一格空着，AI 也不会自己回来。 */
let editingPath='',deferredRender=false;
async function editNote(td){
	let typing=td.querySelector('textarea.note-edit');
	if(typing){typing.focus();return}
	let path=td.dataset.path,item=items.find(x=>x.path===path);
	let cur=String((item&&item.note)||'').replace(/\r\n/g,'\n').trim();
	let ai=(item&&!item.aiHidden&&item.aiDescription&&item.aiDescription.summary)?String(item.aiDescription.summary).trim():'';   /* 你动过的格子不再载入 AI 那句 */
	let aiLine=ai?('AI：'+ai):'';
	let start=cur?(aiLine?(cur+'\n'+aiLine):cur):aiLine;   /* 改的时候 AI 那句也载入，方便对照；最后以你写的为准 */
	let old=td.innerHTML;
	td.innerHTML='<textarea class="note-edit" rows="3" spellcheck="false" autocomplete="off" title="Enter 保存 · Shift+Enter 换行 · Ctrl+Enter 也保存 · Esc 取消 · 上面那行「AI：…」你可以改、可以删：留着它保存＝接受它的内容（并入你自己的话），删掉它＝不要那部分"></textarea>';
	let inp=td.querySelector('textarea.note-edit');
	inp.value=start;
	inp.focus();
	let caret=cur?cur.length:start.length;
	try{inp.setSelectionRange(caret,caret)}catch(_){}
	let closed=false,wasEditing=editingPath;
	editingPath=path;
	const shut=()=>{
		closed=true;
		if(editingPath===path)editingPath=wasEditing;
		if(!editingPath&&deferredRender){deferredRender=false;setTimeout(()=>{if(!editingPath)render()},0)}   /* 攒下的 AI 结果等你改完再画 */
	};
	const finish=async save=>{
		if(closed)return;
		let raw=save?inp.value.replace(/\r\n/g,'\n'):'';
		if(!save||raw===start){shut();td.innerHTML=old;return}   /* 没动过就不写盘 */
		let v=raw;
		if(aiLine)v=v.split(aiLine).join(ai);   /* 你留着 AI 那句＝接受它：内容并入你自己的话，只去掉「AI：」这个来源标记 */
		v=v.trim();
		let hideAI=!v;   /* 全删干净＝这一格以后空着，AI 也不会自己回来 */
		if(!native()||typeof native().set_note!=='function'){toast('改说明仅桌面版可用',true);shut();td.innerHTML=old;return}
		let d;
		try{d=await native().set_note(path,v,hideAI)}catch(e){d={ok:false,error:e.message}}
		if(!d||!d.ok){toast('保存失败：'+((d&&d.error)||'未知错误'),true);shut();td.innerHTML=old;return}
		if(item){item.note=(d.result&&d.result.note)||'';item.aiHidden=!!(d.result&&d.result.aiHidden)}
		shut();
		td.innerHTML=item?aiBox(item):old;
		if(item)td.title=item.aiHidden?'双击可以改这一格（这一格已经是你的话，AI 不再单独显示）；想让 AI 重新说一遍就按住 Shift 点「AI 分析」':'双击可以改这一格，或者按 Enter；单击不会进去';
		let msg=hideAI?'已删除，这一格不再有 AI':(aiLine?'已保存（AI 那句并入你的话）':'已保存');
		toast(msg);
		infoDone(msg,false)
	};
	inp.onclick=e=>e.stopPropagation();
	inp.onblur=()=>finish(true);
	inp.onkeydown=e=>{
		if(e.isComposing||e.keyCode===229)return;   /* 中文输入法选词时按的回车不算保存 */
		if(e.key==='Enter'&&!e.shiftKey&&!e.altKey){e.preventDefault();finish(true)}   /* V2.9：回车就保存；要换行请按 Shift+Enter */
		else if(e.key==='Escape'){e.preventDefault();finish(false)}
	};
}
/* ---------- V1.3：右键菜单 / 忽略名单 / AI 分析 ---------- */
function refreshCounts(){let g=groupItems();el('count').textContent=g.length;el('size').textContent=fmt(g.reduce((a,x)=>a+x.size,0));el('drop').textContent=g.filter(x=>x.recommendation==='不用保住').length;el('risky').textContent=g.filter(x=>x.suspicious).length}
function dropItems(set){items=items.filter(x=>!set.has(String(x.path).toLowerCase()));[...chosen].forEach(id=>{if(!items.find(x=>x.id===id))chosen.delete(id)});render();refreshCounts()}
let ctxTarget=null;
function closeCtx(){let m=el('ctxMenu');if(m){m.classList.remove('open');m.innerHTML='';m.style.left='';m.style.top=''}}
function openCtx(ev,tr){
 let item=items.find(x=>x.path===tr.dataset.path);if(!item)return;
 if(!chosen.has(item.id)&&chosen.size){
  chosen=new Set([item.id]);render();update();
  let rows=el('body').querySelectorAll('tr[data-path]');
  for(let r of rows)if(r.dataset.path===item.path){tr=r;break}
 }
 let multi=chosen.has(item.id)&&chosen.size>1,targets=multi?items.filter(x=>chosen.has(x.id)):[item],paths=targets.map(x=>x.path);
 ctxTarget={item:item,tr:tr,paths:paths,targets:targets,multi:multi};
 let anyKeep=targets.some(x=>x.manualKeep),anyUnkept=targets.some(x=>!x.manualKeep);
 let cnt='<span class="ctx-count">'+paths.length+' 项</span>',suffix=multi?(' '+cnt):'';
 let m=el('ctxMenu');
 m.innerHTML='<div class="ctx-head">'+(multi?('已选 '+paths.length+' 项'):esc(item.displayName||item.name))+'</div>'
  +'<button data-act="ai" title="'+(multi?('对勾选的 '+paths.length+' 个项目做 DeepSeek 分析（分析过的、你动过的会跳过）'):'对这个项目做 DeepSeek 分析（你标注过的会先问一句，确认后深挖子目录重做）')+'">AI 分析'+suffix+'</button>'
  +'<button data-act="note"'+(multi?' disabled title="多选时不可用：说明是按单个项目改的，只勾选一个再右键"':' title="改这一格：框里会载入「AI：…」那句，留着保存＝接受它并并入你的话；删掉＝不要那部分（双击那一格也能改，或用键盘按 Enter）"')+'>改这一格的说明</button>'
  +'<div class="ctx-sep"></div>'
  +'<button data-act="keep"'+(anyUnkept?(' title="把'+(multi?('这 '+paths.length+' 个项目'):'这个项目')+'标为保留：永久留用，不再出现在清理建议里"'):' disabled title="选中的项目都已标为保留，不需要重复操作"')+'>标为保留'+suffix+'</button>'
  +'<button data-act="unkeep"'+(anyKeep?' title="取消「保留」标记，取消后按磁盘实际情况重新评估建议"':' disabled title="选中的项目都没有「保留」标记，不需要取消"')+'>取消保留'+suffix+'</button>'
  +'<div class="ctx-sep"></div>'
  +'<button data-act="ignore" title="写进本机忽略名单，以后扫描直接跳过（不删除任何文件）">忽略（以后扫描跳过）'+suffix+'</button>'
  +'<button data-act="open"'+(multi?' disabled title="多选时不可用：一次只能打开一个目录"':' title="在资源管理器里打开这个包所在的目录"')+'>打开所在目录</button>'
  +'<div class="ctx-sep"></div>'
  +'<button data-act="move" title="选一个目标目录，把这些项目整体搬过去（不删除文件）">转移到其他目录…'+suffix+'</button>'
  +'<button data-act="del" class="danger" title="移到 Windows 回收站，还能从回收站还原">移到回收站'+suffix+'</button>';
 m.querySelectorAll('button').forEach(b=>b.onclick=e=>{e.stopPropagation();if(b.disabled)return;runCtx(b.dataset.act)});
 m.classList.add('open');
 let w=m.offsetWidth||230,h=m.offsetHeight||300,x=ev.clientX||0,y=ev.clientY||0;
 m.style.left=Math.max(6,Math.min(x,window.innerWidth-w-8))+'px';
 m.style.top=Math.max(6,Math.min(y,window.innerHeight-h-8))+'px';
}async function runCtx(act){
 let t=ctxTarget;closeCtx();if(!t)return;
if(act==='note'){if(t.multi){toast('多选时不能改说明：请只勾选一个项目再右键。');return}let td=t.tr.querySelector('td.llm');if(td)editNote(td);return}
 if(act==='ai'){await aiAnalyzePaths(t.paths,false);return}
 if(act==='keep'){await keepRows(t.paths);return}
 if(act==='unkeep'){await unkeepRows(t.paths);return}
 if(act==='ignore'){await ignoreRows(t.targets);return}
 if(act==='open'){if(t.multi){toast('「打开所在目录」一次只能打开一个。');return}let d=await native().open_path(t.item.parentPath||t.item.path);if(!d||!d.ok)toast((d&&d.error)||'打开失败',true);return}
 if(act==='move'){openMoveDialog(t.paths);return}
 if(act==='del'){await deleteRows(t.paths);return}
}async function enrichRows(paths,force,skipped,deep){
	let api=native();
	if(!api||typeof api.enrich!=='function')return alert('AI 分析仅桌面版可用');
	if(!paths||!paths.length)return alert('没有需要分析的项目');
	let cfg=await api.get_settings();
	if(!cfg||!cfg.ok)return alert((cfg&&cfg.error)||'读取设置失败');
	if(!cfg.result.apiKeyMasked)return alert('尚未配置 DeepSeek API Key，请先点右上角「模型设置」填写并保存。');
	if(cfg.result.keyFormatProblem)return alert('⚠️ '+cfg.result.keyFormatProblem+'\n\n请到 DeepSeek 控制台重新复制 Key（形如 sk- 开头共 35 位）后再试。');
	await enrich(paths,false,!!force,skipped||0,!!deep)
}
/* 把要分析的路径分成「要跑的」和「跳过的」：分析过的跳过，你标注过的也跳过（以你的为准） */
function aiTodo(paths,force){
	let todo=[],analyzed=[],touched=0;
	for(let p of paths){
		let it=items.find(x=>x.path===p);
		if(!it)continue;
		if(p===editingPath)continue;   /* 正在改的这一格先不动 */
		if(!force&&(String(it.note||'').trim()||it.aiHidden)){touched++;continue}   /* 你动过的格子默认跳过，AI 不覆盖你的内容 */
		if(it.aiDescription&&!force)analyzed.push(it);
		if(force||!it.aiDescription)todo.push(p)
	}
	return {todo:todo,analyzed:analyzed,touched:touched}
}
async function aiAnalyzePaths(paths,force){
	let picked=paths.map(p=>items.find(x=>x.path===p)).filter(Boolean);
	let touched=picked.filter(x=>String(x.note||'').trim()||x.aiHidden);
	let deep=false;
	/* 只分析这一项、而这一格是你自己动过的：先问一句；确认＝重做，并深挖子目录（你的话一个字不动） */
	if(touched.length&&picked.length===1&&!force){
		if(!await uiConfirm('这一格你自己改过（或把 AI 那句删掉了）。\n继续＝重新问一次 AI，把新的说明加到下面，你写的一个字都不动。','继续分析'))return;
		force=true;deep=true
	}
	let r=aiTodo(paths,force);
	if(!r.todo.length){
		if(r.touched){infoDone('这 '+r.touched+' 项你自己动过，已跳过（你的内容不会被 AI 覆盖）。想让它重新说一次，就只勾选这一项再点「AI 分析」。',false);return}
		infoDone('这 '+r.analyzed.length+' 项上次分析过（'+analyzedAgo(r.analyzed)+'），文件没变，不用再分析。要重做就按住 Shift 点「AI 分析」。',false);return
	}
	await enrichRows(r.todo,force,r.analyzed.length+r.touched,deep)
}
async function aiAnalyze(force){
	let paths=chosen.size?selectedPaths():groupItems().filter(x=>!x.aiDescription&&!String(x.note||'').trim()&&!x.aiHidden).map(x=>x.path);
	if(!paths.length){infoDone('表格里的项目都已有 AI 说明或者你自己动过了，不用再分析。想重做就先勾选项目再点「AI 分析」。',false);return}
	await aiAnalyzePaths(paths,!!force)
}
async function keepRows(paths){
 let api=native();
 if(!api||typeof api.keep!=='function')return alert('仅桌面版可用');
 let d=await api.keep(paths);
 if(!d.ok)return alert(d.error);
 let want=new Set(paths.map(p=>String(p).toLowerCase())),n=0;
 for(let x of items)if(want.has(String(x.path).toLowerCase())){x.recommendation='保留（手工）';x.score=100;x.manualKeep=true;x.reasons=['你在右键菜单里刚标为保留；重新扫描不会覆盖'];n++}
 render();refreshCounts();
 alert('已标为保留 '+n+' 项。这些包不会再被建议清理，重新扫描也不会覆盖。')
}
async function ignoreRows(targets){
 let api=native();
 if(!api||typeof api.ignore!=='function')return alert('忽略名单仅桌面版可用');
 let names=[...new Set(targets.map(x=>x.name))];
 if(!await uiConfirm('确认忽略 '+names.length+' 个项目？\n'+names.slice(0,8).join('\n')+(names.length>8?'\n…（共 '+names.length+' 个）':'')+'\n\n只写进本机忽略名单，不删除任何文件；以后扫描会按这些名字跳过。','忽略'))return;
 let errs=[];
 for(let x of targets){let d=await api.ignore(x.name,x.path);if(!d.ok)errs.push(x.name+'：'+(d.error||'未知错误'))}
 dropItems(new Set(targets.map(x=>String(x.path).toLowerCase())));
 el('scanBar').textContent='已忽略 '+names.length+' 个项目，重新扫描时不会再出现（设置 → 忽略名单 里可恢复）';
 infoDone('已忽略 '+names.length+' 个项目',false);
 if(errs.length)toast('部分项目忽略失败：\n'+errs.slice(0,5).join('\n'),true);
 else toast('已忽略 '+names.length+' 个项目（设置 → 忽略名单 里可恢复）')
}
async function deleteRows(paths){
 let api=native();
 if(!api||typeof api.recycle!=='function')return alert('仅桌面版可用');
 if(!await uiConfirm('确认把 '+paths.length+' 项移到 Windows 回收站？（还能从回收站还原）','移到回收站'))return;
 let d=await api.recycle(paths);
 if(!d.ok)return alert(d.error);
 let done=(d.result||[]);
 dropItems(new Set(done.map(p=>String(p).toLowerCase())));
 alert('已移到回收站 '+done.length+' 项')
}
/* V2.9：设置 → 忽略名单 分成两个标签：「搜索目录」（扫描时跳过）和「AI 分析」（你动过、批量分析不再覆盖的那几格）。 */
let settingsIgnoreTab='scan';
const IGNORE_HINT_SCAN='名单里的项目名称在扫描时会被跳过（不删除任何文件）。想让它重新出现就点「恢复」，再点工具栏的「重新扫描」。';
const IGNORE_HINT_AI='这些格子你自己动过（改写过，或者把「AI：…」那句删干净了），批量 AI 分析会跳过它们，你写的字一个字不动。想让 AI 再说一遍就点右边的「让 AI 重新分析」：新的「AI：…」会加在你写的话下面。';
function ignoreTabCount(which,n){let s=el(which==='ai'?'ignoreTabAiCount':'ignoreTabScanCount');if(s)s.textContent=(typeof n==='number'&&n>0)?('（'+n+'）'):''}
function syncIgnoreTabUI(){
 document.querySelectorAll('.ignore-tabs .seg-btn').forEach(b=>b.classList.toggle('active',b.dataset.ignoreTab===settingsIgnoreTab));
 let hint=el('ignoreHint');
 if(hint)hint.textContent=settingsIgnoreTab==='ai'?IGNORE_HINT_AI:IGNORE_HINT_SCAN
}
function switchIgnoreTab(tab){settingsIgnoreTab=(tab==='ai')?'ai':'scan';syncIgnoreTabUI();loadIgnorePane()}
async function refreshAiSkipCount(){
 if(settingsIgnoreTab==='ai')return;   /* AI 那一页自己会更新计数 */
 let api=native();
 if(!api||typeof api.ai_skip_list!=='function'){ignoreTabCount('ai',0);return}
 let d;try{d=await api.ai_skip_list()}catch(e){d={ok:false}}
 ignoreTabCount('ai',(d&&d.ok&&Array.isArray(d.result))?d.result.length:0)
}
async function loadAiSkipPane(){
 let body=el('ignoreBody');if(!body)return;
 let api=native();
 if(!api||typeof api.ai_skip_list!=='function'){ignoreTabCount('ai',0);body.innerHTML='<p class="muted">这一页仅桌面版可用。</p>';return}
 let d;try{d=await api.ai_skip_list()}catch(e){d={ok:false,error:e.message}}
 if(!d||!d.ok){body.innerHTML='<p class="muted">读取 AI 分析名单失败：'+esc((d&&d.error)||'未知错误')+'</p>';return}
 let recs=Array.isArray(d.result)?d.result:[];
 ignoreTabCount('ai',recs.length);
 body.innerHTML=recs.length?recs.map(r=>{
  let note=String(r.note||'').trim(),why=r.reason==='改写'?'你改写成了自己的话':'你把 AI 那句删掉了';
  return '<div class="ignore-row ai"><span class="ignore-main"><b>'+esc(r.name||r.path)+'</b>'
   +'<div class="ignore-meta">'+esc(why)+(r.when?' · '+esc(String(r.when).replace('T',' ')):'')+'</div>'
   +(note?'<div class="ignore-note">'+esc(note.length>90?note.slice(0,90)+'…':note)+'</div>':'')
   +'<div class="ignore-meta">'+esc(r.path||'')+'</div></span>'
   +'<button class="mini" data-ai-path="'+esc(r.path||'')+'" title="只对「'+esc(r.name||r.path)+'」再问一次 AI：新的「AI：…」加在你写的话下面，你写的字一个不动">让 AI 重新分析</button></div>'
 }).join(''):'<p class="muted">这里还空着。你在表格里改过某一格的说明（或者把「AI：…」那句删干净）保存之后，这一格就会出现在这里：批量 AI 分析默认跳过它们，不会覆盖你写的话。</p>';
 body.querySelectorAll('button[data-ai-path]').forEach(b=>b.onclick=async()=>{
  let path=b.dataset.aiPath;
  if(!path)return;
  b.disabled=true;
  el('settingsModal').classList.remove('open');
  let it=items.find(x=>x.path===path);
  try{await (it?aiAnalyzePaths([path],true):enrich([path],false,true))}catch(e){toast('重新分析失败：'+((e&&e.message)||e),true)}
  b.disabled=false;
  if(settingsIgnoreTab==='ai')loadAiSkipPane()
 })
}
async function loadIgnorePane(){
 let body=el('ignoreBody');if(!body)return;
 syncIgnoreTabUI();
 if(settingsIgnoreTab==='ai')return loadAiSkipPane();
 let api=native();
 if(!api||typeof api.ignored_list!=='function'){body.innerHTML='<p class="muted">忽略名单仅桌面版可用。</p>';return}
 let d;try{d=await api.ignored_list()}catch(e){d={ok:false,error:e.message}}
 if(!d||!d.ok){body.innerHTML='<p class="muted">读取忽略名单失败：'+esc((d&&d.error)||'未知错误')+'</p>';return}
 let recs=d.result||[]; ignoreTabCount('scan',recs.length);refreshAiSkipCount();
 body.innerHTML=recs.length?recs.map(r=>'<div class="ignore-row"><span>'+esc(r.name)+(r.addedAt?'<div class="muted" style="font-size:12px">加入于 '+esc(String(r.addedAt).replace('T',' '))+'</div>':'')+'</span><button class="mini" data-name="'+esc(r.name)+'" title="把「'+esc(r.name)+'」从忽略名单里移除，重新扫描后它会再次出现">恢复</button></div>').join(''):'<p class="muted">名单是空的。在表格里右键任一项目选「忽略」，或勾选后点工具栏的「设为忽略」就能加进来。</p>';
 body.querySelectorAll('button[data-name]').forEach(b=>b.onclick=async()=>{
  let name=b.dataset.name;b.disabled=true;
  let r;try{r=await api.unignore(name)}catch(e){r={ok:false,error:e.message}}
  b.disabled=false;
  if(!r||!r.ok)return toast('恢复失败：'+((r&&r.error)||'未知错误'),true);
  await loadIgnorePane();
  toast('已恢复「'+name+'」，点工具栏的「重新扫描」就能重新看到它');
 });
}
async function openIgnoreList(){return openSettings('ignore')}
/* ---------- V1.4：转移弹窗 / 取消保留 / 深浅主题 ---------- */
function validDest(p){return /^[a-zA-Z]:[\\/]/.test(p)||/^\\\\/.test(p)}
function openMoveDialog(paths){
 paths=(paths||[]).filter(Boolean);
 if(!paths.length)return alert('请先勾选要转移的项目。');
 moveTargets=paths;
 let names=paths.map(p=>String(p).split(/[\\/]/).filter(Boolean).pop()||p);
 el('moveSelected').textContent=names.length<=3?names.join('、'):(names.slice(0,3).join('、')+' 等 '+names.length+' 项');
 el('moveDest').value=lastDestination||'';
 let res=el('moveResult');res.textContent='';res.className='move-result';
 let recent=el('moveRecent');recent.innerHTML='';
 if(lastDestination){
  let chip=document.createElement('button');
  chip.type='button';chip.className='chip';chip.textContent='上次用过：'+lastDestination;
  chip.onclick=()=>{el('moveDest').value=lastDestination};
  recent.appendChild(chip);
 }
 let btn=el('moveConfirm');
 btn.textContent='开始转移';btn.disabled=false;
 el('moveModal').classList.add('open');
 setTimeout(()=>{let d=el('moveDest');d.focus();d.select()},30);
}
async function moveBrowse(){
 let api=native();
 if(!api||typeof api.pick_folder!=='function')return alert('选择目录仅桌面版可用');
 let d;
 try{d=await api.pick_folder()}catch(e){d={ok:false,error:e.message}}
 if(!d||d.cancelled)return;
 if(!d.ok)return alert('选择目录失败：'+((d&&d.error)||'未知错误'));
 el('moveDest').value=d.result||'';
}
async function runMove(){
 let api=native();
 if(!api||typeof api.move!=='function')return alert('转移仅桌面版可用');
 if(!moveTargets.length)return alert('没有要转移的项目。');
 let dest=el('moveDest').value.trim(),res=el('moveResult'),btn=el('moveConfirm');
 if(!dest)return alert('请先填写或选择目标目录。');
 if(!validDest(dest)){res.className='move-result err';res.textContent='目标目录要写成绝对路径，例如 F:\\下载包归档 或 \\\\NAS\\归档。';return}
 btn.disabled=true;btn.textContent='正在转移…';
 res.className='move-result';res.textContent='正在转移 '+moveTargets.length+' 项，请稍候…';
 let d;
 try{d=await api.move(moveTargets,dest)}catch(e){d={ok:false,error:e.message}}
 if(!d||!d.ok){
  btn.disabled=false;btn.textContent='重试';
  res.className='move-result err';res.textContent='转移失败：'+((d&&d.error)||'未知错误');
  return;
 }
 let r=d.result||{},done=r.done||[],failed=r.failed||[];
 if(done.length){
  lastDestination=dest;
  if(typeof api.save_settings==='function'){try{await api.save_settings({destination:dest})}catch(_){}}
 }
 dropItems(new Set(done.map(x=>String(x.from).toLowerCase())));
 moveTargets=failed.map(x=>x.path).filter(Boolean);
 let lines=['已转移 '+done.length+' 项'+(failed.length?('，'+failed.length+' 项未处理（已留在列表里）'):'')+'。'];
 if(failed.length){
  failed.slice(0,5).forEach(x=>lines.push((x.path||'')+'（'+(x.error||'未知错误')+'）'));
  if(failed.length>5)lines.push('…其余 '+(failed.length-5)+' 项略');
 }
 res.className=failed.length?'move-result err':'move-result';
 res.textContent=lines.join('\n');
 btn.disabled=false;
 if(moveTargets.length)btn.textContent='重试剩余 '+moveTargets.length+' 项';
 else btn.textContent='完成';
 el('status').textContent='已转移 '+done.length+' 项到 '+dest;
 infoDone('已转移 '+done.length+' 项到 '+dest,false);
}
async function unkeepRows(paths){
 let api=native();
 if(!api||typeof api.unkeep!=='function')return alert('取消保留仅桌面版可用');
 paths=(paths||[]).filter(Boolean);
 if(!paths.length)return;
 if(!await uiConfirm('确认取消保留 '+paths.length+' 项？\n取消后会按磁盘实际情况重新评估建议，不再固定为「保留」。','取消保留'))return;
 let d;
 try{d=await api.unkeep(paths)}catch(e){d={ok:false,error:e.message}}
 if(!d||!d.ok)return alert('取消失败：'+((d&&d.error)||'未知错误'));
 let result=d.result||{},refreshed=result.refreshed||[],removed=result.removed||[];
 if(!removed.length)return alert('这些项目本来就没有「手工保留」标记。');
 let byPath=new Map(refreshed.map(f=>[String(f.path||'').toLowerCase(),f])),n=0;
 for(let x of items){
  let f=byPath.get(String(x.path).toLowerCase());
  if(!f)continue;
  delete x.manualKeep;
  Object.assign(x,f);
  if(f.manualKeep)x.manualKeep=true;
  n++;
 }
 render();refreshCounts();
 let miss=removed.length-n;
 toast('已取消保留 '+removed.length+' 项'+(refreshed.length?'，建议已重新评估':'')+(miss>0?('（'+miss+' 项不在当前列表，可能已被移动或忽略）'):''));
 el('status').textContent='已取消保留 '+removed.length+' 项'+(refreshed.length?'，建议已重新评估':'');
 infoDone('已取消保留 '+removed.length+' 项',false);
}
const THEME_KEY='dpm-theme';
let themeMode='system';
function systemDark(){return !!(window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches)}
function readThemeMode(){let v='';try{v=localStorage.getItem(THEME_KEY)||''}catch(_){}return (v==='light'||v==='dark')?v:'system'}
function syncThemeButtons(){document.querySelectorAll('.seg-btn[data-theme]').forEach(b=>b.classList.toggle('active',b.dataset.theme===themeMode))}
function paintTheme(){
 let dark=themeMode==='dark'||(themeMode==='system'&&systemDark());
 document.documentElement.classList.toggle('dark',dark);
 let b=el('themeBtn');
 if(b){b.textContent=dark?'☀':'☾';b.title=(dark?'当前是深色，点击切到浅色':'当前是浅色，点击切到深色')+'（设置 → 外观与主题里可以选跟随系统）'}
 syncThemeButtons();
}
function setThemeMode(mode){themeMode=(mode==='light'||mode==='dark')?mode:'system';try{localStorage.setItem(THEME_KEY,themeMode)}catch(_){}paintTheme()}
function toggleTheme(){setThemeMode(document.documentElement.classList.contains('dark')?'light':'dark')}
function initTheme(){
 themeMode=readThemeMode();paintTheme();
 if(!window.matchMedia)return;
 let mq=window.matchMedia('(prefers-color-scheme: dark)');
 let onChange=()=>{if(themeMode==='system')paintTheme()};
 if(mq.addEventListener)mq.addEventListener('change',onChange);
 else if(mq.addListener)mq.addListener(onChange);
}
el('body').addEventListener('contextmenu',ev=>{let tr=ev.target.closest('tr[data-path]');if(!tr)return;ev.preventDefault();openCtx(ev,tr)});
document.addEventListener('click',ev=>{if(!ev.target.closest('#ctxMenu'))closeCtx()});
document.addEventListener('keydown',ev=>{if(ev.key!=='Escape')return;if(el('confirmModal').classList.contains('open'))return;closeCtx();el('settingsModal').classList.remove('open');el('moveModal').classList.remove('open');el('askModal').classList.remove('open')});
window.addEventListener('blur',closeCtx);
el('aiAnalyze').onclick=e=>aiAnalyze(!!(e&&e.shiftKey));
el('keep').onclick=()=>action('keep');
el('unkeep').onclick=()=>{
 let paths=selectedItems().filter(x=>x.manualKeep).map(x=>x.path);
 if(!paths.length)return toast('勾选的项目都没有「保留」标记，不需要取消。');
 unkeepRows(paths);
};
el('ignore').onclick=()=>{
 let targets=selectedItems();
 if(!targets.length)return toast('请先在左侧勾选项目。');
 ignoreRows(targets);
};
/* ---------- V3.0：模型中心——多个常用模型，按服务商分组、可搜索，每个模型单独保存 ----------
   约定：模型列表与「当前默认」由后端分开存储（models.json 里 profiles + defaultId，用稳定 ID 关联）；
   这里只负责草稿：改字段、切换服务商、刷新列表都不会自动保存、也不会自动联网；
   Key 只活在弹窗的内存里：#mKey 留空＝不动已保存的那把，明文永远不写 localStorage。 */
let modelCatalog={providers:[],clientTypes:[],defaultProviderId:'deepseek'};
let modelState={profiles:[],defaultId:'',default:null};
let modelDraft=null;
let modelEditingId='';
let modelSearchText='';
let modelBusy=false;
function modelsApi(){ let api=native(); return (api&&typeof api.get_models==='function')?api:null }
function setModelStatus(text,kind){
 let box=el('modelStatus'); if(!box)return;
 box.textContent=String(text||'');
 box.className='model-status'+(kind?(' '+kind):'')
}
function setVerifyResult(text,kind){
 let box=el('mVerifyResult'); if(!box)return;
 box.textContent=String(text||'');
 box.className='model-verify'+(kind?(' '+kind):'')
}
function providerOf(id){ return (modelCatalog.providers||[]).find(p=>p.id===id)||null }
function providerName(id){ let p=providerOf(id); if(p)return p.name; return id==='custom'?'自定义':(id||'未分组') }
function clientTypeName(id){ let ct=(modelCatalog.clientTypes||[]).find(x=>x.id===id); return ct?ct.name:(id||'openai-chat') }
function modelById(id){ return (modelState.profiles||[]).find(p=>p.id===id)||null }
function newModelId(){ return 'm_'+Date.now().toString(36)+Math.random().toString(36).slice(2,6) }
function suggestModelName(pid,model){ return providerName(pid)+(model?(' · '+model):'') }
async function loadModelCatalog(){
 if((modelCatalog.providers||[]).length)return modelCatalog;
 let api=modelsApi(),d=null;
 if(api&&typeof api.model_catalog==='function'){try{d=await api.model_catalog()}catch(_){d=null}}
 if(d&&d.ok&&d.result&&(d.result.providers||[]).length){ modelCatalog=d.result; return modelCatalog }
 modelCatalog={providers:[],defaultProviderId:'custom',clientTypes:[
  {id:'openai-chat',name:'OpenAI Chat',path:'/chat/completions',hint:''},
  {id:'openai-responses',name:'OpenAI Responses',path:'/responses',hint:''},
  {id:'anthropic-messages',name:'Anthropic Messages',path:'/messages',hint:''}]};
 return modelCatalog
}
/* 只读：从后端拿已保存的模型列表与当前默认，绝不含明文 Key */
async function loadModels(){
 let list=el('modelList'); if(!list)return;
 let api=modelsApi();
 if(!api){ list.innerHTML='<div class="model-empty">模型列表只能在桌面版里读取。</div>'; return }
 await loadModelCatalog();
 let d;try{d=await api.get_models()}catch(e){d={ok:false,error:e.message}}
 if(!d||!d.ok){ list.innerHTML=''; setModelStatus('读取模型配置失败：'+((d&&d.error)||'未知错误'),'err'); return }
 modelState=d.result||{profiles:[],defaultId:'',default:null};
 renderModelList();
 let bits=[],dd=modelState.default;
 if(modelState.migrated)bits.push('已把旧版设置里的配置读进来，点某个模型的「保存」或「设置为默认」才会写成 models.json');
 if(dd)bits.push('当前默认：'+(dd.name||dd.model||'')+(dd.configured?'':'（还没配齐，AI 功能不可用）'));
 let savedCount=(modelState.profiles||[]).length,pending=(modelState.suggested||[]).length;
 if(savedCount>1)bits.push('已保存 '+savedCount+' 个模型');
 if(pending)bits.push('另有 '+pending+' 个常见服务商没配 Key：点它的「填 Key」，粘进去就行');
 setModelStatus(bits.join('　·　'),(dd&&!dd.configured)?'err':'')
}
function modelCardHtml(p){
 if(p.preset){
  let meta=[clientTypeName(p.clientType),p.model,p.baseUrl].filter(Boolean);
  return '<div class="model-card preset" data-provider="'+esc(p.providerId)+'">'
   +'<div class="model-main"><div class="model-name"><span class="model-dot" title="还没有 API Key：点右边的「填 Key」"></span>'
   +'<span class="nm" title="'+esc(p.name)+'">'+esc(p.name)+'</span><span class="model-badge mute">未配置</span></div>'
   +'<div class="model-meta">'+esc(meta.join(' · '))+'</div></div>'
   +'<div class="model-acts"><button type="button" class="mini" data-model-fill="'+esc(p.providerId)+'" title="填一把 '+esc(p.providerName)+' 的 API Key 就能用：地址和型号已经按预置填好，不用自己填">填 Key</button></div></div>'
 }
 let ok=!!p.configured;
 let dotTitle=ok?'必要字段都齐了（服务商、接口地址、型号、Key）':('还没配齐：'+(p.hasKey?'接口地址或型号没填':'还没有 API Key'));
 let badge=p.isDefault?'<span class="model-badge">当前默认</span>':'';
 if(!ok)badge+='<span class="model-badge mute">未配齐</span>';
 let meta=[clientTypeName(p.clientType),(p.model||'（未填型号）')];
 if(p.baseUrl)meta.push(p.baseUrl);
 meta.push(p.hasKey?('Key '+p.keyMasked):'未配置 Key');
 let acts='<button type="button" class="mini" data-model-edit="'+esc(p.id)+'" title="打开这个模型：改字段、测试连通、保存或设为默认">编辑</button>';
 if(!p.isDefault)acts+='<button type="button" class="mini" data-model-default="'+esc(p.id)+'" title="保存这个模型已存的内容，并立即切换为默认模型">设为默认</button>';
 return '<div class="model-card'+(p.isDefault?' current':'')+'" data-id="'+esc(p.id)+'">'
  +'<div class="model-main"><div class="model-name"><span class="model-dot'+(ok?' on':'')+'" title="'+esc(dotTitle)+'"></span>'
  +'<span class="nm" title="'+esc(p.name)+'">'+esc(p.name)+'</span>'+badge+'</div>'
  +'<div class="model-meta">'+esc(meta.join(' · '))+'</div></div>'
  +'<div class="model-acts">'+acts+'</div></div>'
}
function renderModelList(){
 let list=el('modelList'); if(!list)return;
 let all=(modelState.profiles||[]).concat(modelState.suggested||[]);
 if(!all.length){
  list.innerHTML='<div class="model-empty">还没有模型。点上面的「＋ 添加模型」加一个：选服务商 → 填型号和 Key → 想马上用就点「设置为默认」。</div>';
  return
 }
 let q=String(modelSearchText||'').trim().toLowerCase();
 let shown=all.filter(p=>{
  if(!q)return true;
  return [p.name,p.providerName,providerName(p.providerId),p.model,p.baseUrl,clientTypeName(p.clientType)].join(' ').toLowerCase().indexOf(q)>=0
 });
 if(!shown.length){
  list.innerHTML='<div class="model-empty">没有匹配「'+esc(modelSearchText)+'」的模型。清空搜索框就能看全部 '+all.length+' 个。</div>';
  return
 }
 let order=[];(modelCatalog.providers||[]).forEach(p=>order.push(p.id));
 shown.forEach(p=>{ if(order.indexOf(p.providerId)<0)order.push(p.providerId) });
 let html='';
 order.forEach(pid=>{
  let rows=shown.filter(p=>p.providerId===pid);
  if(!rows.length)return;
  rows.sort((a,b)=>((b.isDefault?1:0)-(a.isDefault?1:0))||((a.preset?1:0)-(b.preset?1:0)));
  html+='<div class="model-group" data-provider="'+esc(pid)+'">'
   +'<div class="model-group-head">'+esc(providerName(pid))+'<span class="model-badge mute">'+rows.length+'</span></div>'
   +rows.map(modelCardHtml).join('')+'</div>'
 });
 list.innerHTML=html;
 list.querySelectorAll('[data-model-edit]').forEach(b=>b.onclick=()=>openModelModal(b.dataset.modelEdit,''));
 list.querySelectorAll('[data-model-fill]').forEach(b=>b.onclick=()=>openModelModal('',b.dataset.modelFill));
 list.querySelectorAll('[data-model-default]').forEach(b=>b.onclick=()=>setDefaultModel(b.dataset.modelDefault))
}
function renderProviderOptions(){
 let sel=el('mProvider');
 if(sel){
  let cur=sel.value;
  sel.innerHTML=(modelCatalog.providers||[]).map(p=>'<option value="'+esc(p.id)+'">'+esc(p.name)+'</option>').join('');
  if(cur)sel.value=cur
 }
 let ct=el('mClientType');
 if(ct){
  let v=ct.value;
  ct.innerHTML=(modelCatalog.clientTypes||[]).map(x=>'<option value="'+esc(x.id)+'">'+esc(x.name)+'</option>').join('');
  if(v)ct.value=v
 }
}
function renderModelDatalist(pid){
 let box=el('mModelOptions'); if(!box)return;
 let preset=providerOf(pid)||{models:[]};
 box.innerHTML=(preset.models||[]).map(m=>'<option value="'+esc(m.id)+'">'+esc(m.name)+'</option>').join('')
}
function syncClientTypeHint(){
 let hint=el('mClientTypeHint'),ct=el('mClientType'); if(!hint||!ct)return;
 let info=(modelCatalog.clientTypes||[]).find(x=>x.id===ct.value);
 hint.textContent=info?(info.name+' → 请求 '+(info.path||'')+(info.hint?('　'+info.hint):'')):''
}
/* 弹窗里的只读信息块：服务商、型号、接口地址、接口类型——这些默认按预置填好，用户只需要管 Key */
function syncModelSummary(){
 let box=el('mSummary'); if(!box)return;
 let pid=String((el('mProvider')&&el('mProvider').value)||(modelDraft&&modelDraft.providerId)||'custom');
 let rows=[['服务商',providerName(pid)],
  ['型号',String((el('mModel')&&el('mModel').value)||'').trim()],
  ['接口地址',String((el('mBaseUrl')&&el('mBaseUrl').value)||'').trim()],
  ['接口类型',clientTypeName(String((el('mClientType')&&el('mClientType').value)||''))]];
 box.innerHTML=rows.map(r=>'<span class="k">'+esc(r[0])+'</span><span class="v">'+esc(r[1]||'—')+'</span>').join('')
}

function syncKeyState(){
 let box=el('mKeyState'); if(!box)return;
 if(modelDraft&&modelDraft.hasKey){
  let src=modelDraft.keySource==='env'?'（来自本机环境变量 DEEPSEEK_API_KEY）':(modelDraft.keySource==='file'?'（来自本机加密备份）':'');
  box.textContent='已保存：'+(modelDraft.keyMasked||'')+src+'　留空＝不改这把；想换就直接粘新的进来'
 }else{
  box.textContent='这个模型还没有 Key：填一把再保存（Key 加密存本机，界面只显示尾号）'
 }
}
function blankProfile(id,pid){
 let preset=providerOf(pid)||providerOf('custom')||{id:'custom',name:'自定义',baseUrl:'',clientType:'openai-chat',models:[]};
 let first=(preset.models&&preset.models[0])?preset.models[0].id:'';
 return {id:id,providerId:preset.id,providerName:preset.name,name:suggestModelName(preset.id,first),
  baseUrl:preset.baseUrl||'',model:first,clientType:preset.clientType||'openai-chat',
  hasKey:false,keyMasked:'',keySource:'',isDefault:false}
}
async function openModelModal(id,providerId){
 await loadModelCatalog();
 renderProviderOptions();
 id=String(id||'');
 let p=modelById(id),isNew=!p;
 if(isNew){
  let pid=providerId||(modelCatalog.providers[0]||{}).id||'custom';
  modelEditingId=newModelId();
  modelDraft=blankProfile(modelEditingId,pid)
 }else{
  modelEditingId=p.id;
  modelDraft={id:p.id,providerId:p.providerId,providerName:p.providerName,name:p.name,baseUrl:p.baseUrl,model:p.model,
   clientType:p.clientType,hasKey:!!p.hasKey,keyMasked:p.keyMasked||'',keySource:p.keySource||'',isDefault:!!p.isDefault}
 }
 let advNeeded=isNew&&(!providerId||providerId==='custom');
 el('modelTitle').textContent=isNew?(advNeeded?'添加模型':('填 API Key · '+providerName(modelDraft.providerId))):('编辑模型 · '+(p.name||''));
 if(el('mAdvanced'))el('mAdvanced').open=advNeeded;
 el('mName').value=modelDraft.name||suggestModelName(modelDraft.providerId,modelDraft.model);
 if(modelDraft.providerId)el('mProvider').value=modelDraft.providerId;
 el('mBaseUrl').value=modelDraft.baseUrl||'';
 if(modelDraft.clientType)el('mClientType').value=modelDraft.clientType;
 el('mModel').value=modelDraft.model||'';
 el('mKey').value='';el('mKey').type='password';el('mKeyShow').textContent='显示';
 el('mKeyClear').checked=false;el('mKeyClear').disabled=!modelDraft.hasKey;
 el('mDelete').hidden=isNew||!!modelDraft.isDefault||(modelState.profiles||[]).length<=1;
 el('mDelete').title=modelDraft.isDefault?'默认模型不能删：先给别的模型点「设为默认」，再回来删它':'把这个模型从列表里删掉（其他模型不受影响）';
 renderModelDatalist(modelDraft.providerId);syncClientTypeHint();syncKeyState();syncModelSummary();setVerifyResult('','');
 el('modelModal').classList.add('open');
 setTimeout(()=>{try{el(advNeeded?'mBaseUrl':'mKey').focus()}catch(_){}},30)
}
/* 切换服务商：只填「空着的、或者刚好等于旧服务商预置值」的字段——用户自己改过的一律不动 */
function onProviderChange(){
 let pid=String(el('mProvider').value||'custom');
 let preset=providerOf(pid),prev=providerOf(modelDraft&&modelDraft.providerId);
 let prevModels=((prev&&prev.models)||[]).map(m=>m.id);
 let base=String(el('mBaseUrl').value||'').trim();
 if(!base||(prev&&base===String(prev.baseUrl||'').replace(/\/+$/,'')))el('mBaseUrl').value=preset?(preset.baseUrl||''):'';
 let ct=el('mClientType').value;
 if(!ct||(prev&&ct===prev.clientType))el('mClientType').value=preset?(preset.clientType||'openai-chat'):'openai-chat';
 let md=String(el('mModel').value||'').trim();
 let first=((preset&&preset.models)||[])[0];
 let prevFirst=prevModels.length?prevModels[0]:'';
 if(!md||md===prevFirst||prevModels.indexOf(md)>=0)el('mModel').value=first?first.id:'';
 let nm=String(el('mName').value||'').trim();
 let oldSuggest=suggestModelName(prev?prev.id:'',md);
 if(!nm||nm===oldSuggest||nm===suggestModelName(prev?prev.id:'',prevFirst))el('mName').value=suggestModelName(pid,el('mModel').value);
 if(modelDraft)modelDraft.providerId=pid;
 renderModelDatalist(pid);syncClientTypeHint();syncModelSummary();
 setVerifyResult('','')
}
function modelSnapshot(){
 let pid=String((el('mProvider')&&el('mProvider').value)||(modelDraft&&modelDraft.providerId)||'custom');
 return {id:(modelDraft&&modelDraft.id)||modelEditingId,
  providerId:pid,providerName:providerName(pid),
  name:String((el('mName')&&el('mName').value)||'').trim(),
  baseUrl:String((el('mBaseUrl')&&el('mBaseUrl').value)||'').trim(),
  model:String((el('mModel')&&el('mModel').value)||'').trim(),
  clientType:String((el('mClientType')&&el('mClientType').value)||'openai-chat'),
  apiKey:String((el('mKey')&&el('mKey').value)||'').trim(),
  clearApiKey:!!(el('mKeyClear')&&el('mKeyClear').checked)}
}
/* 保存：只提交这一刻确定的快照，并且带上用户明确点了按钮的意图（intent），后端据此防住初始化回填；保存本身不联网 */
async function saveModelDraft(makeDefault){
 let api=modelsApi();
 if(!api||typeof api.save_model_profile!=='function')return toast('仅桌面版可保存模型配置',true);
 if(modelBusy)return;
 let snap=modelSnapshot();
 if(!snap.baseUrl){ if(el('mAdvanced'))el('mAdvanced').open=true; setVerifyResult('还没填接口地址（Base URL），填好再保存。','err'); try{el('mBaseUrl').focus()}catch(_){} return }
 if(!snap.model){ if(el('mAdvanced'))el('mAdvanced').open=true; setVerifyResult('还没填模型型号，填好再保存。','err'); try{el('mModel').focus()}catch(_){} return }
 if(!snap.apiKey&&!modelDraft.hasKey&&!snap.clearApiKey){ setVerifyResult('还没有可用的 API Key：填一把再保存（保存本身不联网，配好可以点「测试连通」）。','err'); try{el('mKey').focus()}catch(_){} return }
 modelBusy=true; setVerifyResult(makeDefault?'正在保存并设为默认…':'正在保存…','');
 try{
  let d;
  try{ d=await api.save_model_profile(Object.assign({intent:'user-confirmed',makeDefault:!!makeDefault},snap)) }catch(e){ d={ok:false,error:e.message} }
  if(!d||!d.ok)throw Error((d&&d.error)||'保存失败');
  modelState=d.result||modelState;
  let saved=modelById(snap.id)||{};
  modelEditingId=saved.id||snap.id;
  modelDraft=Object.assign({},modelDraft,{id:modelEditingId,hasKey:!!saved.hasKey,keyMasked:saved.keyMasked||'',keySource:saved.keySource||'',isDefault:!!saved.isDefault});
  el('mKey').value='';el('mKey').type='password';el('mKeyShow').textContent='显示';
  el('mKeyClear').checked=false;el('mKeyClear').disabled=!modelDraft.hasKey;
  el('modelTitle').textContent='编辑模型 · '+(saved.name||snap.name||'');
  el('mDelete').hidden=!!saved.isDefault||(modelState.profiles||[]).length<=1;
  syncKeyState();syncModelSummary();renderModelList();
  if(makeDefault){
   el('modelModal').classList.remove('open');
   setModelStatus('已把「'+(saved.name||snap.name||'')+'」设为默认模型，AI 分析 / 智能搜索马上就用它','ok');
   toast('已设为默认：'+(saved.name||snap.name||''))
  }else{
   setVerifyResult('已保存（默认模型没变）','ok');
   setModelStatus('已保存「'+(saved.name||snap.name||'')+'」；默认模型还是「'+(((modelState.default||{}).name)||'—')+'」','ok');
   toast('已保存：'+(saved.name||snap.name||'')+'（默认模型没变）')
  }
  refreshLlmReady()
 }catch(err){
  setVerifyResult('保存失败：'+((err&&err.message)||err),'err')
 }finally{
  modelBusy=false
 }
}
/* 测试连通：只测这份草稿（含还没保存的改动），不写盘、不改默认，结果只显示在这个弹窗里 */
async function verifyModelDraft(){
 let api=modelsApi();
 if(!api||typeof api.verify_model_profile!=='function')return toast('仅桌面版可测试连通',true);
 let btn=el('mVerify'); if(btn)btn.disabled=true;
 setVerifyResult('正在测试连通（只发一条很小的请求）…','');
 try{
  let d;
  try{ d=await api.verify_model_profile(modelSnapshot()) }catch(e){ d={ok:false,error:e.message} }
  if(!d||!d.ok)throw Error((d&&d.error)||'测试失败');
  let r=d.result||{};
  if(!r.ok){ setVerifyResult('连通测试失败：'+(r.error||'未知错误'),'err'); return }
  let bits=['连通正常'];
  if(r.latencyMs!=null)bits.push(r.latencyMs+' ms');
  if(r.keyTail)bits.push('Key 尾号 '+r.keyTail);
  if(r.reply)bits.push('模型回了「'+r.reply+'」');
  setVerifyResult(bits.join(' · ')+'　（只测试：没保存、默认模型也没变）','ok')
 }catch(err){
  setVerifyResult('连通测试失败：'+((err&&err.message)||err),'err')
 }finally{
  if(btn)btn.disabled=false
 }
}
/* 列表上的「设为默认」：把已存的这份配置设为默认（不改字段），立即生效 */
async function setDefaultModel(id){
 let api=modelsApi();
 if(!api)return toast('仅桌面版可修改模型配置',true);
 let p=modelById(id); if(!p)return;
 if(p.isDefault)return toast('「'+p.name+'」已经是默认模型了');
 if(!p.hasKey&&!await uiConfirm('「'+p.name+'」还没有 Key，设成默认后 AI 功能会不可用。\n确定要设成默认吗？','仍然设为默认'))return;
 let d;
 try{ d=await api.save_model_profile({intent:'user-confirmed',id:id,makeDefault:true}) }catch(e){ d={ok:false,error:e.message} }
 if(!d||!d.ok)return toast('设置默认失败：'+((d&&d.error)||'未知错误'),true);
 modelState=d.result||modelState; renderModelList();
 let now=modelById(id)||{};
 setModelStatus('已把「'+(now.name||'')+'」设为默认模型，AI 分析 / 智能搜索马上就用它','ok');
 toast('已设为默认：'+(now.name||''));
 refreshLlmReady()
}
async function deleteCurrentModel(){
 let api=modelsApi();
 if(!api||typeof api.delete_model_profile!=='function')return toast('仅桌面版可修改模型配置',true);
 let p=modelById(modelDraft&&modelDraft.id);
 if(!p)return toast('这个模型还没保存过，直接关掉窗口就行');
 if(p.isDefault)return toast('默认模型不能删：先给别的模型点「设为默认」，再回来删它',true);
 if(!await uiConfirm('确认删除模型「'+p.name+'」？\n只删这条配置，不动任何文件；它存的 Key 会一起删掉，删了就回不来。','删除'))return;
 let d;
 try{ d=await api.delete_model_profile({intent:'user-confirmed',id:p.id}) }catch(e){ d={ok:false,error:e.message} }
 if(!d||!d.ok)return setVerifyResult('删除失败：'+((d&&d.error)||'未知错误'),'err');
 modelState=d.result||modelState; renderModelList();
 el('modelModal').classList.remove('open');
 setModelStatus('已删除「'+p.name+'」','');
 toast('已删除：'+p.name)
}
/* 默认模型变了以后，标题行的问答框锁 / 备份按钮状态跟着刷新（只读，不写盘） */
async function refreshLlmReady(){
 let api=native();
 if(!api||typeof api.get_settings!=='function')return;
 try{
  let d=await api.get_settings();
  if(d&&d.ok){
   let c=d.result||{};
   llmReady=!!c.apiKeyMasked;
   if(el('restoreKey'))el('restoreKey').hidden=!c.keyBackup;
   syncQa();if(typeof syncKb==='function')syncKb()
  }
 }catch(_){}
}
if(el('modelAdd'))el('modelAdd').onclick=()=>openModelModal('','');
if(el('modelSearch'))el('modelSearch').oninput=()=>{modelSearchText=el('modelSearch').value;renderModelList()};
['mProvider','mModel','mBaseUrl','mClientType','mName'].forEach(function(id){
 let box=el(id); if(!box)return;
 box.addEventListener('input',syncModelSummary);box.addEventListener('change',syncModelSummary)
});
if(el('settingsSaveOptions'))el('settingsSaveOptions').onclick=saveSettingsOptions;
if(el('modelClose'))el('modelClose').onclick=()=>el('modelModal').classList.remove('open');
if(el('mCancel'))el('mCancel').onclick=()=>el('modelModal').classList.remove('open');
if(el('modelModal'))el('modelModal').onclick=ev=>{if(ev.target===el('modelModal'))el('modelModal').classList.remove('open')};
if(el('mSave'))el('mSave').onclick=()=>saveModelDraft(false);
if(el('mSetDefault'))el('mSetDefault').onclick=()=>saveModelDraft(true);
if(el('mVerify'))el('mVerify').onclick=verifyModelDraft;
if(el('mDelete'))el('mDelete').onclick=deleteCurrentModel;
if(el('mProvider'))el('mProvider').onchange=onProviderChange;
if(el('mClientType'))el('mClientType').onchange=syncClientTypeHint;
if(el('mKeyShow'))el('mKeyShow').onclick=()=>{
 let box=el('mKey'),show=box.type==='password';
 box.type=show?'text':'password';
 el('mKeyShow').textContent=show?'隐藏':'显示'
};
if(el('mKeyClear'))el('mKeyClear').onchange=()=>{
 if(el('mKeyClear').checked)setVerifyResult('保存后会删掉这个模型已存的 Key；想换 Key 就直接粘新的进去。','')
 else setVerifyResult('','')
};

el('themeBtn').onclick=toggleTheme;
el('settingsBtn').onclick=()=>openSettings(settingsPane||'model');
document.querySelectorAll('.settings-nav .nav-item').forEach(b=>b.onclick=()=>switchSettingsPane(b.dataset.pane));document.querySelectorAll('.ignore-tabs .seg-btn').forEach(b=>b.onclick=()=>switchIgnoreTab(b.dataset.ignoreTab));
document.querySelectorAll('.seg-btn[data-theme]').forEach(b=>b.onclick=()=>setThemeMode(b.dataset.theme));
document.querySelectorAll('[data-close-settings]').forEach(b=>b.onclick=()=>el('settingsModal').classList.remove('open'));
el('ignoreClose').onclick=()=>el('settingsModal').classList.remove('open');

let toastEl=el('toast');
if(toastEl)toastEl.onclick=()=>{toastEl.className='toast';if(toastTimer)clearTimeout(toastTimer)};
el('moveBrowse').onclick=moveBrowse;
el('moveCancel').onclick=()=>el('moveModal').classList.remove('open');
el('moveConfirm').onclick=runMove;
el('moveDest').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();runMove()}else if(e.key==='Escape'){e.preventDefault();el('moveModal').classList.remove('open')}};
initTheme();
