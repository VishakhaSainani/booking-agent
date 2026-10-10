document.addEventListener('DOMContentLoaded', () => {
  const chatMessages = document.getElementById('chat-messages');
  const chatForm = document.getElementById('chat-form');
  const chatInput = document.getElementById('chat-input');
  const callerPhoneInput = document.getElementById('caller-phone');
  const btnSeedDemo = document.getElementById('btn-seed-demo');
  const btnReset = document.getElementById('btn-reset');
  const calendarDateInput = document.getElementById('calendar-date');
  const calendarDateLabel = document.getElementById('calendar-date-label');
  const appointmentCards = document.getElementById('appointment-cards');
  const toolsStream = document.getElementById('tools-stream');
  const contactsTableBody = document.getElementById('contacts-table-body');
  const logsTableBody = document.getElementById('logs-table-body');
  const contactsCount = document.getElementById('contacts-count');
  const logsCount = document.getElementById('logs-count');
  const tabButtons = document.querySelectorAll('.tab-btn');

  let conversationHistory = [];

  // Tab switching
  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      tabButtons.forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      const targetId = btn.dataset.tab;
      document.getElementById(targetId)?.classList.add('active');
    });
  });

  // Quick scenario chips
  document.querySelectorAll('.chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const prompt = chip.dataset.prompt;
      chatInput.value = prompt;
      chatForm.dispatchEvent(new Event('submit'));
    });
  });

  // Append a chat message bubble
  function appendMessage(role, text) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role === 'user' ? 'user-msg' : 'assistant-msg'}`;

    const avatar = document.createElement('div');
    avatar.className = 'msg-avatar';
    avatar.textContent = role === 'user' ? '👤' : '🤖';

    const content = document.createElement('div');
    content.className = 'msg-content';

    const p = document.createElement('p');
    p.textContent = text;
    content.appendChild(p);

    const timestamp = document.createElement('span');
    timestamp.className = 'msg-timestamp';
    timestamp.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    content.appendChild(timestamp);

    msgDiv.appendChild(avatar);
    msgDiv.appendChild(content);

    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  // Render executed tools in sidebar stream
  function renderToolEvents(events) {
    if (!events || events.length === 0) return;

    // Remove empty state if present
    const emptyState = toolsStream.querySelector('.empty-state');
    if (emptyState) emptyState.remove();

    events.forEach(ev => {
      const card = document.createElement('div');
      let toolClass = 'tool-card';
      if (ev.tool_name === 'escalate_to_human') toolClass += ' tool-escalate';
      else if (ev.tool_name === 'book_appointment') toolClass += ' tool-book';
      else if (ev.result?.available === false) toolClass += ' tool-conflict';

      card.className = toolClass;

      const header = document.createElement('div');
      header.className = 'tool-card-header';
      header.innerHTML = `
        <span class="tool-badge">⚡ ${ev.tool_name}</span>
        <span style="font-size: 0.7rem; color: #64748b;">${new Date().toLocaleTimeString()}</span>
      `;
      card.appendChild(header);

      const pre = document.createElement('pre');
      pre.textContent = JSON.stringify({ arguments: ev.arguments, result: ev.result }, null, 2);
      card.appendChild(pre);

      toolsStream.insertBefore(card, toolsStream.firstChild);
    });
  }

  // Fetch and refresh live state from backend
  async function refreshState() {
    try {
      const date = calendarDateInput.value;
      calendarDateLabel.textContent = date;
      const res = await fetch(`/api/state?date=${date}`);
      if (!res.ok) return;
      const data = await res.json();

      // 1. Render Appointments
      appointmentCards.innerHTML = '';
      if (data.appointments.length === 0) {
        appointmentCards.innerHTML = '<div class="empty-state"><p>No appointments booked for this date yet.</p></div>';
      } else {
        data.appointments.forEach(apt => {
          const card = document.createElement('div');
          card.className = 'apt-card';
          const start = new Date(apt.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
          const end = new Date(apt.end_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
          card.innerHTML = `
            <div>
              <div class="apt-title">${apt.customer_name} — ${apt.service_type}</div>
              <div class="apt-meta">${apt.vehicle_type} | ${apt.phone_number || 'N/A'}</div>
            </div>
            <div class="apt-time">${start} – ${end}</div>
          `;
          appointmentCards.appendChild(card);
        });
      }

      // 2. Render Contacts
      contactsTableBody.innerHTML = '';
      contactsCount.textContent = `${data.contacts.length} contacts`;
      data.contacts.forEach(c => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><code>${c.phone_number}</code></td>
          <td><strong>${c.customer_name}</strong></td>
          <td>${c.vehicle_type}</td>
          <td>${c.total_bookings}</td>
          <td>${c.last_contact_date}</td>
          <td>${c.notes || '—'}</td>
        `;
        contactsTableBody.appendChild(tr);
      });

      // 3. Render Call Logs
      logsTableBody.innerHTML = '';
      logsCount.textContent = `${data.call_logs.length} entries`;
      data.call_logs.forEach(l => {
        const tr = document.createElement('tr');
        const followUpHtml = l.needs_human_followup
          ? '<span class="tag-escalate">YES (Follow Up)</span>'
          : '<span style="color: #10b981;">NO</span>';
        const timeFormatted = new Date(l.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        tr.innerHTML = `
          <td>${timeFormatted}</td>
          <td>${l.caller_name} <span style="font-size:0.7rem; color:#64748b;">(${l.caller_phone})</span></td>
          <td><code>${l.call_intent}</code></td>
          <td>${l.outcome}</td>
          <td>${followUpHtml}</td>
          <td title="${l.summary}">${l.summary.slice(0, 40)}...</td>
        `;
        logsTableBody.appendChild(tr);
      });

    } catch (err) {
      console.error('Failed to fetch state:', err);
    }
  }

  // Handle Chat Submit
  chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const message = chatInput.value.trim();
    if (!message) return;

    appendMessage('user', message);
    chatInput.value = '';
    const callerPhone = callerPhoneInput.value.trim();

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: message,
          phone: callerPhone,
          history: conversationHistory,
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      conversationHistory = data.history;
      appendMessage('assistant', data.reply);
      renderToolEvents(data.tool_events);
      await refreshState();
    } catch (err) {
      appendMessage('assistant', 'Sorry, an error occurred while processing your request. Please try again.');
      console.error('Chat error:', err);
    }
  });

  // Seed Demo button
  btnSeedDemo.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/seed-demo', { method: 'POST' });
      const data = await res.json();
      calendarDateInput.value = data.target_date;
      appendMessage('assistant', `⚡ ${data.message}`);
      await refreshState();
      // Switch tab to calendar view to show seeded slot
      document.querySelector('[data-tab="tab-calendar"]')?.click();
    } catch (err) {
      console.error('Seed demo error:', err);
    }
  });

  // Reset button
  btnReset.addEventListener('click', async () => {
    try {
      await fetch('/api/reset', { method: 'POST' });
      conversationHistory = [];
      chatMessages.innerHTML = '';
      appendMessage('assistant', 'Demo state has been reset. How can I help you today?');
      toolsStream.innerHTML = '<div class="empty-state"><span class="empty-icon">⚡</span><p>No tools executed yet.</p></div>';
      await refreshState();
    } catch (err) {
      console.error('Reset error:', err);
    }
  });

  calendarDateInput.addEventListener('change', refreshState);

  // Initial load
  refreshState();
});
