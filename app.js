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
function sortVal(x,k){switch(k){case'name':return (x.displayName||x.name||'').toLowerCase();case'rec':return REC_ORDER[x.recommendation]===undefined?9:REC_ORDER[x.recommendation];case'score':return x.score||0;case'size':return x.size||0;case'modified':return x.modified||'';case'ai':return (x.aiDescription&&x.aiDescription.summary)?1:0;default:return 0}}
function setSort(k){if(sortKey===k)sortDir=-sortDir;else{sortKey=k;sortDir=(k==='name'||k==='rec'||k==='ai')?1:-1}document.querySelectorAll('th.sortable').forEach(th=>{th.classList.remove('asc','desc');if(th.dataset.sort===sortKey)th.classList.add(sortDir>0?'asc':'desc')});render()}
function visible(){let q=el('q').value,f=el('filter').value,r=el('root').value,onlyNew=el('onlyNew').checked;let v=items.filter(x=>(x.group||'download')===activeGroup&&(naturalPaths?naturalPaths.has(x.path):fuzzy([x.name,x.displayName,x.path,x.kind,(x.aiDescription||{}).summary,x.note].join(' '),q))&&(!f||x.recommendation===f)&&(!r||x.root===r)&&(!onlyNew||x.isNew));if(sortKey)v.sort((m,n)=>{let p=sortVal(m,sortKey),q2=sortVal(n,sortKey);return(p<q2?-1:p>q2?1:0)*sortDir});return v}
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
function aiBox(x){let a=x.aiDescription;let when=(a&&a.searchedAt)?'<span class="ai-when" title="这段说明生成于 '+esc(String(a.searchedAt).replace('T',' '))+(a.model?'（'+esc(a.model)+'）':'')+'">'+esc(whenAgo(a.searchedAt))+'</span>':'';let box=a?'<div class="ai"><b>这是：</b>'+esc(a.summary||'')+when+'</div>':'<span class="muted" title="还没有 AI 说明：勾选这一行后点工具栏的「AI 分析」，DeepSeek 会用一句话讲清这是什么包；不点就不会联网。">--</span>';let note=x.note?'<div class="mynote">我的备注：'+esc(x.note)+'</div>':'<div class="note-hint">✎ 点击写备注</div>';return box+note}
function render(){let v=visible();el('body').innerHTML=v.length?v.map(x=>'<tr data-path="'+esc(x.path)+'"><td><input class="pick" type="checkbox" data-id="'+esc(x.id)+'" '+(chosen.has(x.id)?'checked':'')+'></td><td><div class="name">'+esc(x.displayName||x.name)+(x.isNew?' <span class="new">新增</span>':'')+'</div><button class="path open-path" data-path="'+esc(x.parentPath||x.path)+'" title="打开包所在目录">所在目录：'+esc(x.parentPath||x.path)+'</button><div class="muted">'+esc(x.kind)+' · '+x.files+' 文件</div></td><td class="llm" data-path="'+esc(x.path)+'" title="点击可写备注">'+aiBox(x)+'</td><td><span class="badge '+cls(x.recommendation)+'">'+x.recommendation+(x.manualKeep?'<button class="badge-x" data-unkeep="'+esc(x.path)+'" title="取消保留（按实际情况重新评估）">✕</button>':'')+'</span></td><td><b>'+x.score+'</b></td><td>'+fmt(x.size)+'</td><td>'+esc(x.modified.slice(0,10))+'<div class="muted">'+x.ageDays+' 天前</div></td><td>'+esc(x.redownload)+'</td><td class="'+(x.suspicious?'warn':'')+'">'+esc(x.registration)+'</td><td class="why">'+x.reasons.map(esc).join('；')+'</td></tr>').join(''):'<tr><td colspan="10" class="empty">没有符合筛选条件的项目</td></tr>';document.querySelectorAll('.open-path').forEach(e=>e.onclick=async()=>{let d=await native().open_path(e.dataset.path);if(!d.ok)alert(d.error)});document.querySelectorAll('button.badge-x').forEach(b=>b.onclick=e=>{e.stopPropagation();unkeepRows([b.dataset.unkeep])});document.querySelectorAll('td.llm').forEach(td=>td.onclick=()=>editNote(td));document.querySelectorAll('.pick').forEach(e=>e.onchange=()=>{e.checked?chosen.add(e.dataset.id):chosen.delete(e.dataset.id);update()});update()}function selectedItems(){return items.filter(x=>chosen.has(x.id))}
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
   let missing=items.filter(x=>!x.aiDescription&&(force?x.isNew:true)).map(x=>x.path);
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
		q.title = '自动问答：在这里直接问一句，按 Enter 提交（走「智能搜索」的关键词 + AI 语义，会请求 DeepSeek）';
		q.placeholder = '自动问答：问一句，Enter 提交'
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
	let r = d.result || {}, u = r.usage || {}, bits = [];
	if (box) { box.className = 'kb-answer'; box.textContent = r.answer || '（模型没有给出内容）' }
	if (r.model) bits.push('模型 ' + r.model);
	if (u.prompt) bits.push('送入 ' + u.prompt + ' tokens' + (u.cached ? '（缓存命中 ' + u.cached + '）' : ''));
	if (u.completion) bits.push('回答 ' + u.completion + ' tokens');
	if (r.latencyMs) bits.push((r.latencyMs / 1000).toFixed(1) + ' 秒');
	if (r.kb && r.kb.tokens) bits.push('知识库约 ' + r.kb.tokens + ' tokens');
	if (el('kbMeta')) el('kbMeta').textContent = bits.join(' · ')
}
function applySettingsState(c) {
	if (!c) return;
	llmReady = !!c.apiKeyMasked;
	hideNotice = !!c.hideNotice;
	if (el('showNotice')) el('showNotice').checked = !hideNotice;
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
	if (!text) { toast('先输入一句想找什么，例如「哪些安装包很久没动了」'); q.focus(); return }
	el('q').value = text; el('searchStatus').textContent = '';
	searchVersion++; naturalPaths = null;
	q.value = '';
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
async function enrich(paths, quiet = false, force = false, skipped = 0) {
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
		try { d = await native().enrich(group, !!force) } catch (e) { d = { ok: false, error: e.message } }
		if (d && d.result) for (let x of items) if (d.result[x.path]) x.aiDescription = d.result[x.path];
		render();
		if (!d || !d.ok) errors.push(...Object.values((d && d.errors) || { error: (d && d.error) || '未知错误' }))
	}
	enrichRunning--;
	let ok = !errors.length;
	let tail = skipped ? ('（另 ' + skipped + ' 项已分析过，跳过）') : '';
	el('status').textContent = ok ? ('DeepSeek 分析完成并已缓存' + (skipped ? ' · 跳过 ' + skipped + ' 项已分析过的' : '')) : ('分析完成，失败 ' + errors.length + ' 项（可选择后重试）');
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
 let local=items.filter(x=>{let t=[x.name,x.displayName,x.path,x.kind,(x.aiDescription||{}).summary,x.note].join(' ').toLowerCase();return qterms.some(w=>t.includes(w));}).map(x=>x.path);
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
 let api=native();
 if(!api||typeof api.get_settings!=='function'){el('keyStatus').textContent='设置仅桌面版可修改';return}
 let d;try{d=await api.get_settings()}catch(e){d={ok:false,error:e.message}}
 if(!d||!d.ok)return toast('读取设置失败：'+((d&&d.error)||'未知错误'),true);
 let c=d.result||{};
 el('baseUrl').value=c.baseUrl||'';el('model').value=c.model||'';el('autoAnalyze').checked=!!c.autoAnalyze;el('scanAI').checked=!!c.scanAI;el('apiKey').value='';
 if(el('showNotice'))el('showNotice').checked=!c.hideNotice;
 applySettingsState(c);
 let src=c.keySource==='env'?'（来自环境变量 '+c.keyName+'）':(c.keySource==='file'?'（存在本机配置文件里，建议改成环境变量）':'');
 let s=c.apiKeyMasked?('已配置：'+c.apiKeyMasked+src):'尚未配置';
 if(c.keyFormatProblem){s+='　⚠️ '+c.keyFormatProblem;el('keyStatus').style.color='var(--danger-fg)'}
 else el('keyStatus').style.color='var(--fg-faint)';
 el('keyStatus').textContent=s;
}
function switchSettingsPane(pane){
 settingsPane=(pane==='ignore'||pane==='theme'||pane==='guide')?pane:'model';
 document.querySelectorAll('.settings-nav .nav-item').forEach(b=>b.classList.toggle('active',b.dataset.pane===settingsPane));
 document.querySelectorAll('.settings-body .pane').forEach(p=>{p.hidden=(p.dataset.pane!==settingsPane)});
 if(settingsPane==='ignore')loadIgnorePane();
 else if(settingsPane==='theme')syncThemeButtons();
 else if(settingsPane==='guide'){loadKbInfo();syncKb()}
}
async function saveSettings(){
 let d=await native().save_settings({apiKey:el('apiKey').value,baseUrl:el('baseUrl').value,model:el('model').value,autoAnalyze:el('autoAnalyze').checked,scanAI:el('scanAI').checked,hideNotice:el('showNotice')?!el('showNotice').checked:undefined});
 if(!d.ok)return alert(d.error);let r=d.result||{};let msg='设置已保存';
 if(r.keyStoredIn==='env')msg+='\nAPI Key 已写入本机环境变量 '+r.keyName+'（不落盘、不进 Git）';
 else if(r.keyStoredIn==='file')msg+='\n⚠️ 写入环境变量失败，API Key 暂存在本机加密文件里';
 if(r.keyWarning)msg+='\n\n⚠️ Key 格式提醒：'+r.keyWarning;
 el('apiKey').value='';el('settingsModal').classList.remove('open');applySettingsState(r);toast(msg)
}
async function analyzeNow(){if(!native())return alert('AI 分析仅桌面版可用');let d=await native().save_settings({apiKey:el('apiKey').value,baseUrl:el('baseUrl').value,model:el('model').value,autoAnalyze:el('autoAnalyze').checked,scanAI:el('scanAI').checked});if(!d.ok)return alert(d.error);let cfg=await native().get_settings();if(!cfg.ok)return alert(cfg.error);if(!cfg.result.apiKeyMasked)return alert('尚未配置 DeepSeek API Key，请先填写并保存');if(cfg.result.keyFormatProblem)return alert('⚠️ '+cfg.result.keyFormatProblem+'\n\n请到 DeepSeek 控制台重新复制 Key（形如 sk- 开头共 35 位）后再点「立即 AI 分析」。');let missing=groupItems().filter(x=>!x.aiDescription).map(x=>x.path);if(!missing.length){let done=items.filter(x=>x.aiDescription&&x.aiDescription.searchedAt);return alert('所有项目都已有 AI 说明'+(done.length?'（'+analyzedAgo(done)+'分析过）':'')+'，不用再分析。\n想重做的话，回到表格勾选项目后按住 Shift 点工具栏的「AI 分析」。')}el('settingsModal').classList.remove('open');toast('开始 AI 分析 '+missing.length+' 个项目，完成后会提示');await enrich(missing,false)}

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
async function clearKey(){
 if(!native()||typeof native().save_settings!=='function')return alert('仅桌面版可修改设置');
 if(!await uiConfirm('确认清除 DeepSeek API Key（同时删除本机环境变量 DEEPSEEK_API_KEY 与配置文件里的残留）？清除后 AI 说明与智能搜索的语义扩展将不可用。','清除 Key'))return;
 let d=await native().save_settings({clearApiKey:true});
 if(!d.ok)return alert(d.error);
 el('apiKey').value='';el('keyStatus').textContent='尚未配置';
 alert('已清除 API Key')
}
async function testConn(){let btn=el('testConn'),res=el('testResult');btn.disabled=true;res.textContent='正在测试连接…';res.style.color='var(--fg-faint)';try{if(!native()||typeof native().test_connection!=='function')throw Error('连接测试仅桌面版可用');let d=await native().test_connection({baseUrl:el('baseUrl').value,model:el('model').value,apiKey:el('apiKey').value});if(!d.ok)throw Error(d.error||'连接失败');let ok=d.modelOk===false?('模型“'+d.model+'”不在可用列表'):'连接成功';let lat=d.latencyMs!=null?(' · '+d.latencyMs+' ms'):'';let kt=d.keyTail?(' · Key 尾号 '+d.keyTail):'';res.textContent=ok+lat+kt;if(d.modelOk===false&&d.availableModels&&d.availableModels.length)res.textContent+='；可用模型：'+d.availableModels.join('、');res.style.color=d.modelOk===false?'var(--warn-fg)':'var(--ok-fg)';if(d.availableModels&&d.availableModels.length){res.title='可用模型: '+d.availableModels.join(', ');window.diagModels=d.availableModels}}catch(e){res.textContent='连接失败：'+e.message;res.style.color='var(--danger-fg)'}finally{btn.disabled=false}}
document.querySelectorAll('th.sortable').forEach(th=>th.onclick=()=>setSort(th.dataset.sort));el('settingsBtn').onclick=()=>openSettings(settingsPane||'model');el('testConn').onclick=testConn;el('smartSearch').onclick=smartSearch;el('clearKey').onclick=clearKey;el('settingsCancel').onclick=()=>el('settingsModal').classList.remove('open');el('settingsAnalyze').onclick=analyzeNow;el('settingsSave').onclick=saveSettings;el('q').oninput=()=>{searchVersion++;naturalPaths=null;el('searchStatus').textContent='';el('smartSearch').disabled=false;el('smartSearch').classList.remove('searching');el('smartSearch').textContent='智能搜索';render()};el('q').onkeydown=e=>{if(e.key==='Enter')smartSearch()};el('filter').onchange=render;el('onlyNew').onchange=render;el('root').onchange=()=>{if(el('root').value==='__add__'){el('root').value='';addRoot()}else render()};el('rescan').onclick=()=>load(true);el('keep').onclick=()=>action('keep');el('move').onclick=()=>openMoveDialog(selectedPaths());el('del').onclick=()=>action('delete');el('all').onchange=e=>{visible().forEach(x=>e.target.checked?chosen.add(x.id):chosen.delete(x.id));render()};
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
el('kbQ').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();askKb()}else if(e.key==='Escape'){e.preventDefault();el('kbQ').value='';el('kbQ').blur()}};
el('kbQ').onfocus=()=>{if(!llmReady)toast('要使用功能问答，请先到「设置 → 模型设置」中配置 LLM KEY',true)};
syncKb();
syncQa();
let started=false;async function startWhenReady(){if(started)return;let api=native();if(api&&typeof api.scan==='function'&&typeof api.enrich==='function'){started=true;el('status').textContent='原生接口已连接';try{let v=await api.app_version();if(v&&v.ok&&v.result)el('ver').textContent='V'+v.result}catch(_){}try{let gl=await api.group_list();if(gl&&gl.ok&&Array.isArray(gl.result)&&gl.result.length){scanGroups=gl.result.slice();if(!groupOf(activeGroup))activeGroup=scanGroups[0].id;renderTags();fillRootSelect();refreshCounts()}}catch(_){}await load(false);return}el('status').textContent='正在连接本机分析接口…';setTimeout(startWhenReady,200)}window.addEventListener('pywebviewready',startWhenReady);startWhenReady();

async function editNote(td){
 let typing=td.querySelector('input.note-edit');
 if(typing){typing.focus();typing.select();return}
 let path=td.dataset.path,item=items.find(x=>x.path===path),cur=(item&&item.note)||'';
 let old=td.innerHTML;
 td.innerHTML='<input class="note-edit" type="text" maxlength="200" spellcheck="false" autocomplete="off" placeholder="写一句自己的备注，例如：给谁用 / 别删 / 装完就能删">';
 let inp=td.querySelector('input.note-edit');
 inp.value=cur;
 inp.focus();
 inp.select();
 let closed=false;
 const finish=async save=>{
  if(closed)return;
  closed=true;
  let v=inp.value.trim();
  if(!save||v===cur){td.innerHTML=old;return}
  if(!native()||typeof native().set_note!=='function'){toast('备注仅桌面版可保存',true);td.innerHTML=old;return}
  let d;
  try{d=await native().set_note(path,v)}catch(e){d={ok:false,error:e.message}}
  if(!d||!d.ok){toast('备注保存失败：'+((d&&d.error)||'未知错误'),true);td.innerHTML=old;return}
  if(item)item.note=(d.result&&d.result.note)||'';
  td.innerHTML=item?aiBox(item):old;
  toast(v?'备注已保存':'备注已清除');
  infoDone(v?'备注已保存':'备注已清除',false)
 };
 inp.onclick=e=>e.stopPropagation();
 inp.onblur=()=>finish(true);
 inp.onkeydown=e=>{
  if(e.key==='Enter'){e.preventDefault();finish(true)}
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
  +'<button data-act="ai" title="'+(multi?('对勾选的 '+paths.length+' 个项目做 DeepSeek 分析（已有说明会重做）'):'对这个项目做 DeepSeek 分析（已有说明会重做）')+'">AI 分析'+suffix+'</button>'
  +'<button data-act="note"'+(multi?' disabled title="多选时不可用：备注是按单个项目写的，只勾选一个再右键"':' title="给这个项目写一句自己的备注（点「AI 说明：这是个什么包」这一格也能写）"')+'>写 / 改备注</button>'
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
 if(act==='note'){if(t.multi){toast('备注只能一行一行写：多选时请只勾选一个项目再右键。');return}let td=t.tr.querySelector('td.llm');if(td)editNote(td);return}
 if(act==='ai'){await aiAnalyzePaths(t.paths,false);return}
 if(act==='keep'){await keepRows(t.paths);return}
 if(act==='unkeep'){await unkeepRows(t.paths);return}
 if(act==='ignore'){await ignoreRows(t.targets);return}
 if(act==='open'){if(t.multi){toast('「打开所在目录」一次只能打开一个。');return}let d=await native().open_path(t.item.parentPath||t.item.path);if(!d||!d.ok)toast((d&&d.error)||'打开失败',true);return}
 if(act==='move'){openMoveDialog(t.paths);return}
 if(act==='del'){await deleteRows(t.paths);return}
}async function enrichRows(paths,force,skipped){
 let api=native();
 if(!api||typeof api.enrich!=='function')return alert('AI 分析仅桌面版可用');
 if(!paths||!paths.length)return alert('没有需要分析的项目');
 let cfg=await api.get_settings();
 if(!cfg||!cfg.ok)return alert((cfg&&cfg.error)||'读取设置失败');
 if(!cfg.result.apiKeyMasked)return alert('尚未配置 DeepSeek API Key，请先点右上角「模型设置」填写并保存。');
 if(cfg.result.keyFormatProblem)return alert('⚠️ '+cfg.result.keyFormatProblem+'\n\n请到 DeepSeek 控制台重新复制 Key（形如 sk- 开头共 35 位）后再试。');
 await enrich(paths,false,!!force,skipped||0)
}
/* 把要分析的路径分成「需要跑的」和「已经分析过的」 */
function aiTodo(paths,force){
 let todo=[],analyzed=[];
 for(let p of paths){
  let it=items.find(x=>x.path===p);
  if(!it)continue;
  if(it.aiDescription&&!force)analyzed.push(it);
  if(force||!it.aiDescription)todo.push(p)
 }
 return {todo:todo,analyzed:analyzed}
}
async function aiAnalyzePaths(paths,force){
 let r=aiTodo(paths,force);
 if(!r.todo.length){infoDone('这 '+r.analyzed.length+' 项上次分析过（'+analyzedAgo(r.analyzed)+'），文件没变，不用再分析。要重做就按住 Shift 点「AI 分析」。',false);return}
 await enrichRows(r.todo,force,r.analyzed.length)
}
async function aiAnalyze(force){
 let paths=chosen.size?selectedPaths():groupItems().filter(x=>!x.aiDescription).map(x=>x.path);
 if(!paths.length){infoDone('表格里的项目都已有 AI 说明，不用再分析。想重做就先勾选项目再点「AI 分析」。',false);return}
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
async function loadIgnorePane(){
 let body=el('ignoreBody');if(!body)return;
 let api=native();
 if(!api||typeof api.ignored_list!=='function'){body.innerHTML='<p class="muted">忽略名单仅桌面版可用。</p>';return}
 let d;try{d=await api.ignored_list()}catch(e){d={ok:false,error:e.message}}
 if(!d||!d.ok){body.innerHTML='<p class="muted">读取忽略名单失败：'+esc((d&&d.error)||'未知错误')+'</p>';return}
 let recs=d.result||[];
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
document.addEventListener('keydown',ev=>{if(ev.key!=='Escape')return;if(el('confirmModal').classList.contains('open'))return;closeCtx();el('settingsModal').classList.remove('open');el('moveModal').classList.remove('open')});
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
el('themeBtn').onclick=toggleTheme;
el('settingsBtn').onclick=()=>openSettings(settingsPane||'model');
document.querySelectorAll('.settings-nav .nav-item').forEach(b=>b.onclick=()=>switchSettingsPane(b.dataset.pane));
document.querySelectorAll('.seg-btn[data-theme]').forEach(b=>b.onclick=()=>setThemeMode(b.dataset.theme));
document.querySelectorAll('[data-close-settings]').forEach(b=>b.onclick=()=>el('settingsModal').classList.remove('open'));
el('ignoreClose').onclick=()=>el('settingsModal').classList.remove('open');
el('settingsCancel').onclick=()=>el('settingsModal').classList.remove('open');
let toastEl=el('toast');
if(toastEl)toastEl.onclick=()=>{toastEl.className='toast';if(toastTimer)clearTimeout(toastTimer)};
el('moveBrowse').onclick=moveBrowse;
el('moveCancel').onclick=()=>el('moveModal').classList.remove('open');
el('moveConfirm').onclick=runMove;
el('moveDest').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();runMove()}else if(e.key==='Escape'){e.preventDefault();el('moveModal').classList.remove('open')}};
initTheme();
