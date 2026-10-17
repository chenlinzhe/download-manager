let items=[],chosen=new Set(),naturalPaths=null,searchVersion=0,sortKey='',sortDir=1;
const native=()=>window.desktop||window.pywebview?.api;const el=id=>document.getElementById(id);function fmt(n){if(!n)return'0 B';let u=['B','KB','MB','GB','TB'],i=Math.min(4,Math.floor(Math.log(n)/Math.log(1024)));return(n/1024**i).toFixed(i?1:0)+' '+u[i]}function esc(s){return String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}function cls(r){return (r==='建议保留'||r==='保留（手工）')?'keep':r==='待确认'?'review':'drop'}function fuzzy(text,q){text=(text||'').toLowerCase();q=(q||'').toLowerCase().trim();if(!q)return true;return text.includes(q)}const REC_ORDER={'保留（手工）':0,'建议保留':1,'待确认':2,'不用保住':3};
function sortVal(x,k){switch(k){case'name':return (x.displayName||x.name||'').toLowerCase();case'rec':return REC_ORDER[x.recommendation]===undefined?9:REC_ORDER[x.recommendation];case'score':return x.score||0;case'size':return x.size||0;case'modified':return x.modified||'';case'ai':return (x.aiDescription&&x.aiDescription.summary)?1:0;default:return 0}}
function setSort(k){if(sortKey===k)sortDir=-sortDir;else{sortKey=k;sortDir=(k==='name'||k==='rec'||k==='ai')?1:-1}document.querySelectorAll('th.sortable').forEach(th=>{th.classList.remove('asc','desc');if(th.dataset.sort===sortKey)th.classList.add(sortDir>0?'asc':'desc')});render()}
function visible(){let q=el('q').value,f=el('filter').value,r=el('root').value,onlyNew=el('onlyNew').checked;let v=items.filter(x=>(naturalPaths?naturalPaths.has(x.path):fuzzy([x.name,x.displayName,x.path,x.kind,(x.aiDescription||{}).summary,x.note].join(' '),q))&&(!f||x.recommendation===f)&&(!r||x.root===r)&&(!onlyNew||x.isNew));if(sortKey)v.sort((m,n)=>{let p=sortVal(m,sortKey),q2=sortVal(n,sortKey);return(p<q2?-1:p>q2?1:0)*sortDir});return v}
const STOP=new Set(('的了着是在有和与及或也都就才又再还只但并而这那此其某个吗呢吧啊呀哦嗯哈嗦啦喰么之对从向给被把让到于为以用想找要搜查看请帮哪什该我你他她它咱俺种').split(''));['一个','一下','一种','一些','一类','一款','这个','那个','这些','那些','哪个','哪些','这种','那种','哪种','这么','那么','这样','那样','一点','有些','东西','里面','我们','你们','他们','她们','它们','咱们','自己','可以','想要','需要','应该','看看','点儿','有点儿','如何','为什么','a','an','the','of','for','is','are','it','to','and','or','this','that','these','those','want','find','get','with','my','me','one','we','you','they'].forEach(w=>STOP.add(w));
function cutTerms(q){q=(q||'').toLowerCase();let toks=q.match(/[a-z0-9]+|[\u4e00-\u9fff]+/g)||[];let out=[],seen=new Set();for(let t of toks){if(t&&!seen.has(t)){seen.add(t);out.push(t);}}let kept=out.filter(c=>!STOP.has(c));return kept.length?kept:out;}
function aiBox(x){let box=x.aiDescription?'<div class="ai"><b>这是：</b>'+esc(x.aiDescription.summary||'')+'</div>':'<span class="muted">--</span>';let note=x.note?'<div class="mynote">我的备注：'+esc(x.note)+'</div>':'<div class="note-hint">✎ 点击写备注</div>';return box+note}
function render(){let v=visible();el('body').innerHTML=v.length?v.map(x=>'<tr><td><input class="pick" type="checkbox" data-id="'+esc(x.id)+'" '+(chosen.has(x.id)?'checked':'')+'></td><td><div class="name">'+esc(x.displayName||x.name)+(x.isNew?' <span class="new">新增</span>':'')+'</div><button class="path open-path" data-path="'+esc(x.parentPath||x.path)+'" title="打开包所在目录">所在目录：'+esc(x.parentPath||x.path)+'</button><div class="muted">'+esc(x.kind)+' · '+x.files+' 文件</div></td><td class="llm" data-path="'+esc(x.path)+'" title="点击可写备注">'+aiBox(x)+'</td><td><span class="badge '+cls(x.recommendation)+'">'+x.recommendation+'</span></td><td><b>'+x.score+'</b></td><td>'+fmt(x.size)+'</td><td>'+esc(x.modified.slice(0,10))+'<div class="muted">'+x.ageDays+' 天前</div></td><td>'+esc(x.redownload)+'</td><td class="'+(x.suspicious?'warn':'')+'">'+esc(x.registration)+'</td><td class="why">'+x.reasons.map(esc).join('；')+'</td></tr>').join(''):'<tr><td colspan="10" class="empty">没有符合筛选条件的项目</td></tr>';document.querySelectorAll('.open-path').forEach(e=>e.onclick=async()=>{let d=await native().open_path(e.dataset.path);if(!d.ok)alert(d.error)});document.querySelectorAll('td.llm').forEach(td=>td.onclick=()=>editNote(td));document.querySelectorAll('.pick').forEach(e=>e.onchange=()=>{e.checked?chosen.add(e.dataset.id):chosen.delete(e.dataset.id);update()});update()}function update(){el('selected').textContent='已选 '+chosen.size+' 项';el('keep').disabled=el('move').disabled=el('del').disabled=!chosen.size}
async function load(force){
 el('scanBar').textContent=force?'正在全盘重新扫描…':'正在加载扫描结果…';el('scanBar').title='';el('scanBar').style.color='';
 let api=native(),timer=null;
 if(force&&api&&typeof api.scan_status==='function'){timer=setInterval(async()=>{try{let s=await api.scan_status();if(s&&s.phase)el('scanBar').textContent=s.total?('正在'+s.phase+' '+s.done+' / '+s.total+'，请稍候…'):('正在'+s.phase+'…')}catch(_){}},400)}
 try{
  let d=api?await api.scan(!!force):await (await fetch('/api/scan'+(force?'?force=1':''))).json();
  if(d.error)throw Error(d.error);
  items=d.items;chosen.clear();
  el('count').textContent=items.length;
  el('size').textContent=fmt(items.reduce((a,x)=>a+x.size,0));
  el('drop').textContent=items.filter(x=>x.recommendation==='不用保住').length;
  el('risky').textContent=items.filter(x=>x.suspicious).length;
  let prevRoot=el('root').value,roots=d.roots||[];
  el('root').innerHTML='<option value="__add__">＋ 新增目录…</option><option value="">全部目录</option>'+roots.map(x=>'<option>'+esc(x)+'</option>').join('');
  el('root').value=(prevRoot&&roots.indexOf(prevRoot)>=0)?prevRoot:'';
  let errs=d.errors||[];
  el('scanBar').textContent=(force?'已重新扫描 · ':'')+roots.length+' 个目录 · 更新于 '+String(d.generatedAt||'').replace('T',' ')+(force?'':'（复用最近扫描结果，点“重新扫描”立即刷新）')+(errs.length?(' · '+errs.length+' 处读取失败（悬停查看）'):'');
  if(errs.length)el('scanBar').title=errs.slice(0,8).join('\n')+(errs.length>8?'\n…':'');
  else el('scanBar').style.color='';
  if(errs.length)el('scanBar').style.color='#9a6700';
  render();
  if(api){
   let cfg=await api.get_settings();
   if(cfg&&cfg.ok&&!el('dest').value)el('dest').value=cfg.result.destination||'';
   let missing=items.filter(x=>!x.aiDescription&&(force?x.isNew:true)).map(x=>x.path);
   if(cfg&&cfg.ok&&cfg.result.autoSearch&&cfg.result.apiKeyMasked&&missing.length)enrich(missing,true)
  }
 }catch(e){
  el('scanBar').textContent='加载失败';el('body').innerHTML='<tr><td colspan="10" class="empty">'+esc(e.message)+'</td></tr>'
 }finally{if(timer)clearInterval(timer)}
}

async function postAction(url,payload){
 if(native()){let d;if(url==='/api/move')d=await native().move(payload.paths,payload.destination);else if(url==='/api/keep')d=await native().keep(payload.paths);else d=await native().recycle(payload.paths);if(!d.ok)throw Error(d.error);return d}
 let r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),cache:'no-store'}),text=await r.text(),d=JSON.parse(text);if(!r.ok||!d.ok)throw Error(d.error||('HTTP '+r.status));return d
}


async function enrich(paths,quiet=false){if(!native()||!paths.length)return;let errors=[];for(let i=0;i<paths.length;i+=10){let group=paths.slice(i,i+10);el('status').textContent='DeepSeek 并发分析 '+(i+1)+'–'+Math.min(i+group.length,paths.length)+' / '+paths.length;let d=await native().enrich(group);if(d.result)for(let x of items)if(d.result[x.path])x.aiDescription=d.result[x.path];render();if(!d.ok)errors.push(...Object.values(d.errors||{error:d.error||'未知错误'}))}el('status').textContent=errors.length?'分析完成，失败 '+errors.length+' 项（可选择后重试）':'DeepSeek 分析完成并已缓存';if(errors.length&&!quiet)alert('AI 搜索失败：'+errors.join('；'))}
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
}async function addRoot(){let d=await native().add_manual_root();if(d.cancelled)return;if(!d.ok)return alert(d.error);alert('已添加扫描目录：'+d.result);await load(true)}
async function openSettings(){
 let d=await native().get_settings();if(!d.ok)return alert(d.error);let c=d.result||{};
 el('baseUrl').value=c.baseUrl;el('model').value=c.model;el('autoSearch').checked=c.autoSearch;el('apiKey').value='';
 let src=c.keySource==='env'?'（来自环境变量 '+c.keyName+'）':(c.keySource==='file'?'（存在本机配置文件里，建议改成环境变量）':'');
 let s=c.apiKeyMasked?('已配置：'+c.apiKeyMasked+src):'尚未配置';
 if(c.keyFormatProblem){s+='　⚠️ '+c.keyFormatProblem;el('keyStatus').style.color='#cf222e'}else{el('keyStatus').style.color='#636c76'}
 el('keyStatus').textContent=s;el('settingsModal').classList.add('open')
}
async function saveSettings(){
 let d=await native().save_settings({apiKey:el('apiKey').value,baseUrl:el('baseUrl').value,model:el('model').value,autoSearch:el('autoSearch').checked});
 if(!d.ok)return alert(d.error);let r=d.result||{};let msg='设置已保存';
 if(r.keyStoredIn==='env')msg+='\nAPI Key 已写入本机环境变量 '+r.keyName+'（不落盘、不进 Git）';
 else if(r.keyStoredIn==='file')msg+='\n⚠️ 写入环境变量失败，API Key 暂存在本机加密文件里';
 if(r.keyWarning)msg+='\n\n⚠️ Key 格式提醒：'+r.keyWarning;
 el('apiKey').value='';el('settingsModal').classList.remove('open');alert(msg)
}
async function analyzeNow(){if(!native())return alert('AI 分析仅桌面版可用');let d=await native().save_settings({apiKey:el('apiKey').value,baseUrl:el('baseUrl').value,model:el('model').value,autoSearch:el('autoSearch').checked});if(!d.ok)return alert(d.error);let cfg=await native().get_settings();if(!cfg.ok)return alert(cfg.error);if(!cfg.result.apiKeyMasked)return alert('尚未配置 DeepSeek API Key，请先填写并保存');if(cfg.result.keyFormatProblem)return alert('⚠️ '+cfg.result.keyFormatProblem+'\n\n请到 DeepSeek 控制台重新复制 Key（形如 sk- 开头共 35 位）后再点「立即 AI 分析」。');let missing=items.filter(x=>!x.aiDescription).map(x=>x.path);if(!missing.length)return alert('所有项目都已有 AI 说明，无需分析');el('settingsModal').classList.remove('open');alert('开始 AI 分析 '+missing.length+' 个项目，完成后会提示');await enrich(missing,false)}

async function action(type){
 let paths=[...chosen],dest=el('dest').value.trim();
 if(type==='move'&&!dest)return alert('请先填写转移目标目录。');
 let msg=type==='keep'?'确认将所选项目标为“保留”（永久留用，不受清理建议影响）？':type==='move'?'确认将 '+paths.length+' 项转移到：\n'+dest+'\n同名目标不会覆盖。':'确认将 '+paths.length+' 项移到 Windows 回收站？';
 if(!confirm(msg))return;
 let btn=el(type==='keep'?'keep':type==='move'?'move':'del');btn.disabled=true;
 try{
  let d=await postAction(type==='move'?'/api/move':type==='keep'?'/api/keep':'/api/recycle',{paths:paths,destination:dest});
  let n=0,extra='';
  if(type==='move'){
   let r=d.result||{};n=(r.done||[]).length;
   let f=r.failed||[];
   if(f.length)extra='，'+f.length+' 项未处理：\n'+f.slice(0,5).map(x=>(x.path||'')+'（'+(x.error||'')+'）').join('\n')+(f.length>5?'\n（其余 '+(f.length-5)+' 项略）':'');
   if(n&&dest&&native())await native().save_settings({destination:dest});
  }else if(Array.isArray(d.result))n=d.result.length;
  else n=paths.length;
  alert('操作完成，共处理 '+n+' 项'+extra);
  await load(true)
 }catch(e){alert('操作失败：'+e.message)}
 finally{update()}
}
async function clearKey(){
 if(!native()||typeof native().save_settings!=='function')return alert('仅桌面版可修改设置');
 if(!confirm('确认清除 DeepSeek API Key（同时删除本机环境变量 DEEPSEEK_API_KEY 与配置文件里的残留）？清除后 AI 说明与智能搜索的语义扩展将不可用。'))return;
 let d=await native().save_settings({clearApiKey:true});
 if(!d.ok)return alert(d.error);
 el('apiKey').value='';el('keyStatus').textContent='尚未配置';
 alert('已清除 API Key')
}
async function testConn(){let btn=el('testConn'),res=el('testResult');btn.disabled=true;res.textContent='正在测试连接…';res.style.color='#636c76';try{if(!native()||typeof native().test_connection!=='function')throw Error('连接测试仅桌面版可用');let d=await native().test_connection({baseUrl:el('baseUrl').value,model:el('model').value,apiKey:el('apiKey').value});if(!d.ok)throw Error(d.error||'连接失败');let ok=d.modelOk===false?('模型“'+d.model+'”不在可用列表'):'连接成功';let lat=d.latencyMs!=null?(' · '+d.latencyMs+' ms'):'';let kt=d.keyTail?(' · Key 尾号 '+d.keyTail):'';res.textContent=ok+lat+kt;if(d.modelOk===false&&d.availableModels&&d.availableModels.length)res.textContent+='；可用模型：'+d.availableModels.join('、');res.style.color=d.modelOk===false?'#9a6700':'#1a7f37';if(d.availableModels&&d.availableModels.length){res.title='可用模型: '+d.availableModels.join(', ');window.diagModels=d.availableModels}}catch(e){res.textContent='连接失败：'+e.message;res.style.color='#cf222e'}finally{btn.disabled=false}}
document.querySelectorAll('th.sortable').forEach(th=>th.onclick=()=>setSort(th.dataset.sort));el('settingsBtn').onclick=openSettings;el('testConn').onclick=testConn;el('smartSearch').onclick=smartSearch;el('clearKey').onclick=clearKey;el('settingsCancel').onclick=()=>el('settingsModal').classList.remove('open');el('settingsAnalyze').onclick=analyzeNow;el('settingsSave').onclick=saveSettings;el('q').oninput=()=>{searchVersion++;naturalPaths=null;el('searchStatus').textContent='';el('smartSearch').disabled=false;el('smartSearch').classList.remove('searching');el('smartSearch').textContent='智能搜索';render()};el('q').onkeydown=e=>{if(e.key==='Enter')smartSearch()};el('filter').onchange=render;el('onlyNew').onchange=render;el('root').onchange=()=>{if(el('root').value==='__add__'){el('root').value='';addRoot()}else render()};el('rescan').onclick=()=>load(true);el('keep').onclick=()=>action('keep');el('move').onclick=()=>action('move');el('del').onclick=()=>action('delete');el('all').onchange=e=>{visible().forEach(x=>e.target.checked?chosen.add(x.id):chosen.delete(x.id));render()};
let started=false;async function startWhenReady(){if(started)return;let api=native();if(api&&typeof api.scan==='function'&&typeof api.enrich==='function'){started=true;el('status').textContent='原生接口已连接';try{let v=await api.app_version();if(v&&v.ok&&v.result)el('ver').textContent='V'+v.result}catch(_){}await load(false);return}el('status').textContent='正在连接本机分析接口…';setTimeout(startWhenReady,200)}window.addEventListener('pywebviewready',startWhenReady);startWhenReady();

async function editNote(td){
 if(td.querySelector('textarea'))return;
 let path=td.dataset.path,item=items.find(x=>x.path===path),cur=(item&&item.note)||'';
 td.innerHTML='<textarea class="note-edit" rows="3" maxlength="200" placeholder="写点自己的备注，例如：给谁用 / 别删 / 装完就能删"></textarea><div class="note-actions"><button class="mini primary" data-act="save">保存</button><button class="mini" data-act="cancel">取消</button></div>';
 let ta=td.querySelector('textarea');ta.value=cur;ta.focus();ta.select();
 let closed=false;
 const done=async save=>{
  if(closed)return;closed=true;
  if(!save){render();return}
  if(!native()||typeof native().set_note!=='function'){alert('备注仅桌面版可保存');render();return}
  let d;
  try{d=await native().set_note(path,ta.value)}catch(e){d={ok:false,error:e.message}}
  if(!d||!d.ok){alert('备注保存失败：'+((d&&d.error)||'未知错误'));render();return}
  if(item)item.note=(d.result&&d.result.note)||'';
  render()
 };
 td.querySelector('[data-act="save"]').onclick=e=>{e.stopPropagation();done(true)};
 td.querySelector('[data-act="cancel"]').onclick=e=>{e.stopPropagation();done(false)};
 ta.onclick=e=>e.stopPropagation();
 ta.onkeydown=e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();done(true)}else if(e.key==='Escape'){e.preventDefault();done(false)}};
}
