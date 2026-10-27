(function () {
  const form = document.getElementById('sample-qaqc-form');
  const configNode = document.getElementById('w430-edit-config');
  if (!form || !configNode) return;
  const config = JSON.parse(configNode.textContent);
  const pdfButton = document.getElementById('w430-pdf-export');
  if (pdfButton && pdfButton.dataset.exportUrl) {
    pdfButton.addEventListener('click', () => window.location.assign(pdfButton.dataset.exportUrl));
  }
  const excelButton = document.getElementById('w430-excel-export');
  if (excelButton && excelButton.dataset.exportUrl) {
    excelButton.addEventListener('click', () => window.location.assign(excelButton.dataset.exportUrl));
  }
  if (config.submitted) {
    document.querySelectorAll('#w430-sample-edit input, #w430-sample-edit button, #w430-qaqc input').forEach(n => n.disabled = true);
    header();return;
  }
  const tbody = form.querySelector('tbody');
  const rows = () => Array.from(tbody.querySelectorAll('.sample-qaqc-row'));
  const visible = () => rows().filter(r => !r.classList.contains('is-excluded-row'));
  const message = document.getElementById('w430-edit-message');
  const checks = document.getElementById('w430-qaqc');
  function dirty() {
    message.textContent = '本列濃度依稀釋倍數即時更新；請按「更新樣品及 QA/QC」確認全部計算，尚未暫存本次修改。';
    // Hide stale QA/QC until the server recalculates.
    if (checks) checks.hidden = true;
  }
  function order() {
    const list = visible();
    list.forEach((row, i) => {
      row.querySelector('.display-order-text').textContent = i + 1;
      row.querySelector('.display-order-input').value = i + 1;
      row.querySelector('.move-row-up').disabled = !list[i-1] || list[i-1].dataset.w430Group !== row.dataset.w430Group;
      row.querySelector('.move-row-down').disabled = !list[i+1] || list[i+1].dataset.w430Group !== row.dataset.w430Group;
    });
  }
  rows().forEach(row => {
    const role = row.querySelector('input[name^="role_"]').value;
    row.querySelectorAll('input:not([type="hidden"]):not([type="checkbox"])').forEach(input => {
      input.readOnly = !(input.classList.contains('dilution-factor-input') && ['SAMPLE','SAMPLE_BLANK','DUP','MS','MSD'].includes(role));
    });
  });
  function recalculateRow(row) {
    const input = row.querySelector('.dilution-factor-input');
    const cell = row.querySelector('.calculated-concentration-cell');
    const interpretation = row.querySelector('.interpretation-cell');
    const role = row.querySelector('input[name^="role_"]').value;
    if (role === 'SAMPLE_BLANK') {
      cell.textContent = '－';
      row.querySelector('.measured-concentration-cell').textContent = '－';
      return;
    }
    const dilution = Number(input.value);
    const baseText = row.dataset.w430BaseConcentration;
    const base = Number(baseText);
    const valid = input.value.trim() !== '' && Number.isFinite(dilution) && dilution > 0 &&
                  baseText !== undefined && baseText !== '' && Number.isFinite(base);
    const value = valid ? base * dilution : NaN;
    const decimals = Math.max(0, Math.min(8, Number(row.dataset.w430Decimals) || 0));
    cell.textContent = Number.isFinite(value) ? value.toFixed(decimals) : '—';
    if (role === 'SAMPLE') {
      const mdlText = document.getElementById('analysis-mdl').value;
      const mdl = Number(mdlText), qdl = Number(row.dataset.w430BaseQdl) * dilution;
      interpretation.textContent = !Number.isFinite(value) ? '待重新計算' :
        mdlText.trim() !== '' && Number.isFinite(mdl) && value < mdl * dilution ? 'ND' :
        Number.isFinite(qdl) && value < qdl ? '<QDL' : '';
    }
    if (['MS','MSD'].includes(role) && row.dataset.w430BaseSpike !== '') {
      const spike = Number(row.dataset.w430BaseSpike) * dilution;
      row.querySelector('input[name^="spike_concentration_"]').value =
        input.value.trim() !== '' && dilution > 0 && Number.isFinite(spike) ? String(spike) : '';
    }
  }
  form.addEventListener('input', event => {
    if (event.target.classList.contains('dilution-factor-input')) {
      dirty();recalculateRow(event.target.closest('.sample-qaqc-row'));
    }
  });
  form.addEventListener('change', event => {
    if (!event.target.classList.contains('sample-delete-checkbox') || !event.target.checked) return;
    if (!window.confirm('確定刪除此列？刪除原樣品時，重新計算會一併移除其 DUP／MS／MSD 及未共用的 B 空白。')) {event.target.checked=false;return;}
    const row=event.target.closest('.sample-qaqc-row');row.classList.add('is-excluded-row');row.hidden=true;order();dirty();
  });
  form.addEventListener('click', event => {
    const button=event.target.closest('.move-row-up,.move-row-down');
    if (!button || button.disabled) return;
    const row=button.closest('.sample-qaqc-row'), list=visible(), index=list.indexOf(row);
    const other=list[index+(button.classList.contains('move-row-up')?-1:1)];
    if (!other || other.dataset.w430Group!==row.dataset.w430Group) return;
    if (button.classList.contains('move-row-up')) tbody.insertBefore(row,other);
    else tbody.insertBefore(other,row);
    order();dirty();
  });
  function hidden(name,value) {
    const input=document.createElement('input');input.type='hidden';input.name=name;input.value=value;form.appendChild(input);return input;
  }
  const actionInput = hidden('action','recalculate_samples');
  for (const key of ['csrf_token','context_token','preview_token']) hidden(key,config[key]||'');
  const edits=document.createElement('input');edits.type='hidden';edits.name='edits';form.appendChild(edits);
  const remarks = hidden('batch_remarks','{}');
  form.addEventListener('submit', event => {
    const list=rows();
    if (list.some(row => {const v=Number(row.querySelector('.dilution-factor-input').value);return !Number.isFinite(v)||v<=0;})) {
      event.preventDefault();message.textContent='稀釋倍數必須為有效正數。';return;
    }
    const id = event.submitter && event.submitter.id;
    if (id === 'w430-record-save' && !window.confirm('確定儲存分析紀錄並送出待審核？成功後此工作將移出暫存清單。')) {
      event.preventDefault();return;
    }
    actionInput.value = id === 'w430-excel-export' ? 'export_excel' : id === 'w430-pdf-export' ? 'export_pdf' : id === 'w430-record-save' ? 'submit_record' : id === 'w430-draft-save' ? 'save_draft' : 'recalculate_samples';
    const notes = {};
    document.querySelectorAll('#batch-remark-form input[name^="batch_remark_"]').forEach(n => notes[n.name.slice(13)] = n.value);
    remarks.value = JSON.stringify(notes);
    edits.value=JSON.stringify(list.map(row => ({
      id:Number(row.querySelector('input[name^="source_sequence_"]').value),
      dilution:row.querySelector('.dilution-factor-input').value,
      excluded:row.classList.contains('is-excluded-row')
    })));
  });
  document.querySelectorAll('#batch-remark-form input').forEach(n => n.addEventListener('input', () => {
    message.textContent = '批次備註已修改，請暫存或儲存分析紀錄。';
  }));
  const remarkForm = document.getElementById('batch-remark-form');
  if (remarkForm) remarkForm.addEventListener('submit', event => {event.preventDefault();form.requestSubmit();});
  function header() {
    const top = document.querySelector('.page-header');
    // sticky top is relative to .main-content, not viewport coordinates.
    document.documentElement.style.setProperty('--w430-header-bottom', (top ? top.getBoundingClientRect().height : 0) + 'px');
  }
  window.addEventListener('resize', header);
  if (window.ResizeObserver) {
    const top = document.querySelector('.page-header');
    if (top) new ResizeObserver(header).observe(top);
  }
  order();header();
})();
