const $ = (id) => document.getElementById(id);
let currentQuiz = null;
let busy = false;
let noticeTimer;
const quizzes = new Map();
function element(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
}
function notice(text, persistent = false) {
  clearTimeout(noticeTimer); $('notice').textContent = text; $('notice').hidden = false;
  if (!persistent) noticeTimer = setTimeout(() => { $('notice').hidden = true; }, 12000);
}
async function api(path, options = {}) {
  const response = await fetch('/api/' + path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Проверь введённые данные.');
  return data;
}
const post = (path, data) => api(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
async function action(task) {
  if (busy) return;
  busy = true;
  document.querySelectorAll('button').forEach(b => b.disabled = true);
  try { await task(); } catch (error) { notice(error.message); }
  finally { busy = false; document.querySelectorAll('button').forEach(b => b.disabled = false); }
}
function show(tab) {
  document.querySelectorAll('.panel').forEach(p => p.classList.toggle('active', p.id === tab));
  document.querySelectorAll('.nav').forEach(n => n.classList.toggle('active', n.dataset.tab === tab));
  if (tab === 'plan') refreshProgress().catch(e => notice(e.message));
}
document.querySelectorAll('[data-tab]').forEach(b => b.onclick = () => show(b.dataset.tab));
function sourceDetails(sources) {
  const details = element('details', undefined, 'sources');
  details.append(element('summary', `Источники · ${sources.length}`));
  for (const source of sources) {
    const block = element('div', undefined, 'source');
    block.append(element('strong', source.source + (source.page ? ` · стр. ${source.page}` : '') + ' / ' + source.section));
    block.append(element('p', source.text));
    block.append(element('code', `[${source.id}]`)); details.append(block);
  }
  return details;
}
function message(role, text, result) {
  const box = element('article', undefined, `message ${role}`);
  box.append(element('div', role === 'user' ? 'ТЫ' : 'COURSEPILOT', 'role'));
  box.append(element('div', text, 'answer'));
  if (result?.sources?.length) box.append(sourceDetails(result.sources));
  if (result?.trace?.length) box.append(element('div', result.trace.map(t => t.tool + (t.ok ? ' ✓' : ' !')).join(' → ') + ` · ${(result.latency_ms / 1000).toFixed(1)} с`, 'trace'));
  $('messages').append(box);
  return box;
}
async function send(text) {
  await action(async () => {
    message('user', text);
    const pending = message('assistant', 'Изучаю материалы…');
    try {
      const result = await post('chat', {course: $('course').value, message: text});
      pending.remove();
      const reply = message('assistant', result.answer, result);
      if (result.quiz) { renderQuiz(result.quiz); const button = element('button', 'Открыть тест', 'primary'); button.onclick = () => show('quiz'); reply.append(button); }
      if (result.plan) renderPlan(result.plan);
      $('message').value = '';
      reply.scrollIntoView({behavior: 'smooth', block: 'center'});
    } catch (e) { pending.remove(); throw e; }
  });
}
$('chat-form').onsubmit = e => { e.preventDefault(); const text = $('message').value.trim(); if (text) send(text); };
$('message').onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('chat-form').requestSubmit(); } };
document.querySelectorAll('[data-prompt]').forEach(b => b.onclick = () => send(b.dataset.prompt));
async function refreshCourses(selected) {
  const courses = await api('courses');
  const target = selected || $('course').value;
  $('course').replaceChildren(); $('course-list').replaceChildren();
  for (const course of courses) {
    $('course').append(new Option(course.id === 'ml-foundations' ? 'Основы машинного обучения' : course.id, course.id));
    $('course-list').append(element('div', `${course.id} · документов: ${course.documents} · фрагментов: ${course.chunks}`, 'result'));
  }
  if (!courses.length) $('course').append(new Option('Основы машинного обучения', 'ml-foundations'));
  if ([...$('course').options].some(o => o.value === target)) $('course').value = target;
}
$('seed').onclick = () => action(async () => {
  notice('Индексирую материалы курса…', true);
  const result = await post('seed', {}); await refreshCourses('ml-foundations');
  notice(`Курс готов: ${result.length} документов. Можно задавать вопросы.`);
});
$('upload-form').onsubmit = e => {
  e.preventDefault(); action(async () => {
    const form = new FormData(); const course = $('course-id').value;
    form.append('course', course); form.append('file', $('document').files[0]);
    notice('Обрабатываю документ…', true);
    const result = await api('documents', {method: 'POST', body: form});
    await refreshCourses(course); notice(`Готово: ${result.source}, фрагментов: ${result.chunks}.`);
  });
};
function renderQuiz(quiz) {
  currentQuiz = quiz; quizzes.set($('course').value, quiz);
  const form = element('form'); form.append(element('h3', quiz.title));
  quiz.questions.forEach((q, i) => {
    const field = element('fieldset', undefined, 'quiz-question'); field.append(element('legend', `${i + 1}. ${q.question}`));
    q.options.forEach((text, index) => {
      const label = element('label', undefined, 'option');
      const input = element('input'); input.type = 'radio'; input.name = `q${i}`; input.value = index; input.required = true;
      label.append(input, element('span', text)); field.append(label);
    }); form.append(field);
  });
  const button = element('button', 'Проверить ответы', 'primary'); button.type = 'submit'; form.append(button);
  form.onsubmit = e => { e.preventDefault(); action(async () => {
    const answers = quiz.questions.map((_, i) => Number(new FormData(form).get(`q${i}`)));
    const result = await post(`quiz/${quiz.id}/grade`, {answers});
    form.querySelectorAll('input').forEach(input => input.disabled = true);
    button.remove();
    form.append(element('h3', `Результат: ${Math.round(result.score * 100)}%`));
    result.questions.forEach((q, i) => {
      const field = form.querySelectorAll('fieldset')[i];
      field.append(element('div', `${result.answers[i] === q.correct ? 'Верно' : 'Нужно повторить'}. Правильный ответ: ${q.options[q.correct]}\n${q.explanation}\nИсточник: [${q.source_id}]`, 'explanation'));
    });
    await refreshProgress();
  }); };
  if (quiz.sources?.length) form.append(sourceDetails(quiz.sources));
  $('quiz-content').classList.remove('empty-state'); $('quiz-content').replaceChildren(form);
}
$('quiz-form').onsubmit = e => { e.preventDefault(); action(async () => renderQuiz(await post('quiz', {course: $('course').value, topic: $('quiz-topic').value}))); };
function renderPlan(plan) {
  $('plan-content').replaceChildren(element('h3', plan.goal));
  plan.steps.forEach((step, i) => {
    const box = element('div', undefined, 'step');
    box.append(element('small', `ЗАНЯТИЕ ${i + 1} · ${step.minutes} МИНУТ`), element('h3', step.title), element('p', step.task));
    const relevant = plan.sources.filter(s => step.source_ids.includes(s.id));
    if (relevant.length) box.append(sourceDetails(relevant)); $('plan-content').append(box);
  });
}
async function refreshProgress() {
  const progress = await api('progress?course=' + encodeURIComponent($('course').value));
  $('progress').replaceChildren();
  for (const [label, value] of [['Пройдено тестов', progress.completed_quizzes], ['Средний результат', progress.average_score === null ? '—' : Math.round(progress.average_score * 100) + '%']]) {
    const stat = element('div', label, 'stat'); stat.append(element('strong', String(value))); $('progress').append(stat);
  }
  $('results').replaceChildren();
  progress.results.forEach(r => { const item = element('div', r.topic, 'result'); item.append(element('strong', Math.round(r.score * 100) + '%')); $('results').append(item); });
  if (!progress.results.length) $('results').append(element('p', 'Пройди первый тест — здесь появятся результаты.'));
  if (progress.plan) renderPlan(progress.plan); else $('plan-content').replaceChildren();
}
$('plan-form').onsubmit = e => { e.preventDefault(); action(async () => {
  const plan = await post('plan', {course: $('course').value, topic: $('goal').value, minutes_per_day: Number($('minutes').value)});
  renderPlan(plan); notice('План сохранён.');
}); };
$('course').onchange = () => action(async () => {
  $('messages').replaceChildren();
  const history = await api('history?course=' + encodeURIComponent($('course').value));
  history.forEach(m => message(m.role, m.content));
  currentQuiz = quizzes.get($('course').value) || null;
  if (currentQuiz) renderQuiz(currentQuiz); else { $('quiz-content').replaceChildren(element('p', 'Создай тест для выбранного курса.')); }
  $('course-id').value = $('course').value; await refreshProgress();
});
(async () => {
  try {
    const status = await api('status');
    $('status').textContent = status.configured ? 'Ключ OpenAI настроен' : 'Нужен API-ключ';
    await refreshCourses();
    const history = await api('history?course=' + encodeURIComponent($('course').value));
    history.forEach(m => message(m.role, m.content));
    if (!status.configured) notice('Для ответов добавь ключ OpenAI в .env.local и перезапусти приложение.', true);
  } catch (e) { notice(e.message); }
})();
