'use strict';
Object.assign(enNew, {
  council:'Analyst council', councilDemo:'Demo: question templates only. Connect a local model for substantive analysis.',
  councilLocal:'Local model analysis. Check conclusions against sources.', opportunities:'Opportunities', risks:'Risks',
  missingData:'Missing data', agreements:'Agreements', disagreements:'Disagreements', nextSteps:'Next steps',
  go:'Recommendation: proceed', no_go:'Recommendation: decline', needs_data:'More data needed',
  councilProgress:'Completed stages', councilTransfer:'Prepare instruction',
  councilTransferHelp:'Review the text, choose an assignee and deadline. Tasks require plan approval.',
  councilRevoked:'Source access changed. Start a new council.',
  councilRolesHelp:'Keyword-based automatic selection or 3–5 manually selected roles, including critic.',
  team_selected:'Team selected', synthesis:'Final recommendation', keyword_router_v1:'Automatic composition', explicit_selection:'Your selection',
});
Object.assign(ru, {
  council:'Совет аналитиков', councilSub:'Рассмотрите идею с разных сторон: возможности, риски, разногласия и следующий шаг.',
  councilQuestion:'Идея или вопрос', councilRoles:'Состав совета', councilAuto:'Подобрать автоматически',
  councilRolesHelp:'Автоподбор по ключевым словам или 3–5 ролей вручную, включая критика.',
  councilStart:'Собрать совет', councilBoundary:'Рекомендации для решения руководителя. Все роли используют одну модель и не являются независимыми экспертами.',
  councilDemo:'Демо: шаблон вопросов по ролям. Для содержательного анализа подключите локальную модель.',
  councilLocal:'Анализ локальной модели. Проверяйте выводы по источникам.',
  opportunities:'Возможности', risks:'Риски', missingData:'Недостающие данные', agreements:'Общие выводы',
  disagreements:'Разногласия', nextSteps:'Следующие шаги', go:'Рекомендация: продолжить', no_go:'Рекомендация: отказаться',
  needs_data:'Нужно больше данных', councilProgress:'Завершённые этапы', councilTransfer:'Подготовить поручение',
  councilTransferHelp:'Проверьте текст, укажите ответственного и срок. Задачи появятся после согласования плана.',
  councilRevoked:'Доступ к источникам изменился. Повторите рассмотрение.',
  team_selected:'Команда подобрана', synthesis:'Итоговая рекомендация', keyword_router_v1:'Автоматический подбор', explicit_selection:'Ваш состав совета',
});
const councilPage = el('section',undefined,'page');
councilPage.id='page-council'; councilPage.hidden=true;
// Static markup only. All user/model/source content below is inserted with textContent.
councilPage.innerHTML=`<div class="page-heading"><div><p class="eyebrow">AI OFFICE · ANALYST COUNCIL</p><h1 data-i18n="council">Analyst council</h1><p data-i18n="councilSub">Explore an idea through opportunities, risks, disagreements and a next step.</p></div></div>
<p class="data-note" data-i18n="councilBoundary">Advice for a human decision. Roles share one model and are not independent experts.</p>
<form id="council-form" class="card"><label for="council-question" data-i18n="councilQuestion">Idea or question</label><textarea id="council-question" required minlength="10" maxlength="4000" rows="4"></textarea>
<label for="council-auto" data-i18n="councilRoles">Council composition</label><select id="council-auto"><option value="auto" data-i18n="councilAuto">Select automatically</option><option value="manual">Manual / Вручную</option></select>
<p data-i18n="councilRolesHelp">Keyword-based automatic selection or 3–5 manually selected roles, including critic.</p><div id="council-roles" class="button-row" hidden></div><button type="submit" data-i18n="councilStart">Convene council</button></form>
<article id="council-result" class="card" hidden aria-live="polite"></article><article class="card"><h2 data-i18n="recentRuns">Recent workflows</h2><div id="council-history"></div></article>`;
$('main').append(councilPage);
const councilNav=el('a','Analyst council'); councilNav.href='#council'; councilNav.dataset.page='council'; councilNav.dataset.i18n='council';
$('nav a[data-page="chief"]').after(councilNav);
let councilRegistry=null;
function councilRoleName(id){return bilingual(councilRegistry?.roles.find(r=>r.id===id)?.name||t(id));}
async function loadCouncil(){
  if(!state.actor||location.hash!=='#council')return;
  const allowed=state.actor.role!=='employee'; $('#council-form').hidden=!allowed;
  if(!allowed){clear($('#council-history')).append(el('p',t('restricted')));$('#council-result').hidden=true;return;}
  councilRegistry=await api('/council/roles');
  const selected=[...document.querySelectorAll('#council-roles input:checked')].map(e=>e.value);
  const box=clear($('#council-roles'));
  councilRegistry.roles.forEach(role=>{const label=el('label',councilRoleName(role.id));const input=el('input');input.type='checkbox';input.value=role.id;input.checked=selected.includes(role.id);label.prepend(input);box.append(label);});
  const history=clear($('#council-history'));const runs=await api('/runs?limit=100');
  const councils=runs.filter(r=>r.type==='council');
  if(!councils.length)history.append(el('p',t('empty')));
  councils.forEach(run=>{const item=el('div',undefined,'row');item.append(el('p',new Date(run.created_at*1000).toLocaleString()),badge(run.state),button(t('open'),()=>showRun(run.id)));history.append(item);});
}
function councilPoints(panel, key, values){if(!values?.length)return;const list=el('ul');values.forEach(v=>list.append(el('li',v)));panel.append(el('h3',t(key)),list);}
function councilCitations(panel, ids, evidence){
  ids.forEach(id=>{const source=evidence.find(e=>e.source_id===id);if(source)panel.append(button(id.slice(0,8)+' · v'+source.version,()=>showSource(source.url,source.fragment_ref)));});
}
async function showCouncilRun(run,attempt=0){
  if(!councilRegistry)councilRegistry=await api('/council/roles');
  const panel=clear($('#council-result'));panel.hidden=false;
  panel.append(el('h2',run.input.question),badge(run.state));
  const result=run.result;
  if(result?.status==='evidence_revoked'){panel.append(el('p',t('councilRevoked')));return;}
  if(result){
    panel.append(el('p',t(result.demo?'councilDemo':'councilLocal'),'data-note'));
    if(result.roles)panel.append(el('p',result.roles.map(councilRoleName).join(' · ')),el('small',t(result.routing)+(result.model_id?' · '+result.model_id:'')));
    if(result.error_code)panel.append(el('p',result.error_code));
    councilPoints(panel,'councilProgress',(result.checkpoints||[]).map(c=>councilRoleName(c.step)+' · '+new Date(c.completed_at*1000).toLocaleTimeString()));
    if(result.synthesis){
      const s=result.synthesis;const card=el('div',undefined,'data-note');
      card.append(el('h2',t(s.recommendation)),el('p',s.summary));
      for(const key of ['agreements','disagreements','next_steps'])councilPoints(card,key==='next_steps'?'nextSteps':key,s[key]);
      councilCitations(card,s.source_ids,result.evidence);panel.append(card);
      if(!result.demo&&s.next_steps.length){panel.append(button(t('councilTransfer'),()=>{
        $('#command').value=('На основании рассмотрения: '+run.input.question+'\nПредложенные шаги (проверить перед согласованием):\n'+s.next_steps.join('\n')).slice(0,4000);
        location.hash='chief';notify(t('councilTransferHelp'));
      }));}
    }
    for(const p of result.perspectives||[]){
      const card=el('details',undefined,'plan-task');card.open=true;
      card.append(el('summary',councilRoleName(p.role)),el('p',p.assessment));
      councilPoints(card,'opportunities',p.opportunities);councilPoints(card,'risks',p.risks);councilPoints(card,'missingData',p.missing_data);
      councilCitations(card,p.source_ids,result.evidence);panel.append(card);
    }
    if(result.evidence?.length){panel.append(el('h3',t('sources')));result.evidence.forEach(e=>{
      const item=el('div',undefined,'evidence');item.append(el('small',e.source_id.slice(0,8)+' · v'+e.version+' · '+e.observed_at),el('p',e.fragment),button(t('open'),()=>showSource(e.url,e.fragment_ref)));panel.append(item);
    });}
  }
  if(['received','planning'].includes(run.state)){
    panel.append(button(t('refreshState'),()=>showRun(run.id)));
    const current=++state.poll;
    if(attempt<400)setTimeout(()=>{if(current===state.poll&&state.actor&&location.hash==='#council')guard(()=>showRun(run.id,attempt+1));},2000);
  }else{state.poll++;await loadCouncil();}
}
$('#council-auto').onchange=()=>{$('#council-roles').hidden=$('#council-auto').value==='auto';};
$('#council-form').addEventListener('submit',e=>{e.preventDefault();const b=e.submitter;b.disabled=true;guard(async()=>{try{
  const roles=$('#council-auto').value==='auto'?[]:[...document.querySelectorAll('#council-roles input:checked')].map(input=>input.value);
  if($('#council-auto').value==='manual'&&(roles.length<3||roles.length>5||!roles.includes('critic')))throw new Error(t('councilRolesHelp'));
  const result=await api('/council',{method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()},body:{question:$('#council-question').value,roles}});
  await showRun(result.run_id);
}finally{b.disabled=false;}});});
// Include login/reload and language changes through the existing page entry point.
const originalPage=page;
page=async function(){await originalPage();await loadCouncil();};
translate();
