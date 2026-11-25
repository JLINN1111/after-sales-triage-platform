(() => {
  const panel = document.querySelector('.assistant-panel');
  if (!panel) return;
  const input = panel.querySelector('#assistant_input');
  const history = panel.querySelector('.assistant-history');
  const sendButton = panel.querySelector('.assistant-send');
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  let sessionId = panel.querySelector('.assistant-session-id')?.value || '';

  const fieldNames = ['equipment_type', 'equipment_model', 'occurred_at', 'operating_state', 'shutdown', 'safety_risk', 'alarm_code_status', 'alarm_code', 'submitter_note'];
  const formContext = () => Object.fromEntries(fieldNames.map((name) => [name, document.querySelector(`[name="${name}"]`)?.value || '']));
  const request = async (url, body) => {
    const response = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}, body: JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '助手暂时不可用，请改为手工填写。');
    return data;
  };
  const add = (kind, text) => {
    const item = document.createElement('div');
    item.className = `assistant-message ${kind}`;
    item.textContent = text;
    history.appendChild(item);
  };
  const ensureSession = async () => {
    if (sessionId) return sessionId;
    const endpoint = panel.dataset.mode === 'ticket' ? panel.dataset.ticketUrl : panel.dataset.createUrl;
    const data = await request(endpoint, {});
    sessionId = data.session_id;
    const hidden = panel.querySelector('.assistant-session-id');
    if (hidden) hidden.value = sessionId;
    return sessionId;
  };
  const renderSuggestion = (data) => {
    const fields = Object.keys(data.field_suggestions || {});
    if (!fields.length) return;
    const box = document.createElement('div');
    box.className = 'assistant-suggestion';
    box.textContent = `可采用字段：${fields.map((name) => `${name}=${data.field_suggestions[name]}`).join('；')}`;
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'btn btn-secondary'; button.textContent = '采用建议填入表单';
    button.addEventListener('click', async () => {
      try {
        const applied = await request(`/assistant/sessions/${sessionId}/apply`, {message_id: data.message_id, fields});
        Object.entries(applied.applied_fields).forEach(([field, value]) => {
          const control = document.querySelector(`[name="${field}"]`);
          if (control) control.value = value;
        });
        button.disabled = true; button.textContent = '已填入，提交前请核对';
      } catch (error) { add('error', error.message); }
    });
    box.appendChild(document.createElement('br')); box.appendChild(button); history.appendChild(box);
  };
  sendButton.addEventListener('click', async () => {
    const message = input.value.trim();
    if (!message) return;
    sendButton.disabled = true;
    try {
      await ensureSession();
      add('user', message); input.value = '';
      const data = await request(`/assistant/sessions/${sessionId}/messages`, {message, form_context: formContext()});
      add('assistant', data.reply);
      if (data.urgent_risk_hint) add('warning', '检测到可能的安全风险，请停止继续操作并联系售后人员确认。');
      if ((data.needs_confirmation || []).length) add('hint', `仍需确认：${data.needs_confirmation.join('、')}`);
      renderSuggestion(data);
    } catch (error) { add('error', error.message); }
    finally { sendButton.disabled = false; }
  });
})();
