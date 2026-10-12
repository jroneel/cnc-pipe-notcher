const fields = ['width', 'height', 'wall', 'corner_radius', 'lead_in', 'feed', 'standoff', 'clearance', 'pivot'];
const values = new WeakMap();
const limits = new WeakMap();
const scale = unit => unit === 'in' ? 25.4 : 1;

function millimetres(input, unit) {
  const saved = values.get(input);
  if (saved?.display === input.value) return saved.mm;
  return Number(input.value) * scale(unit);
}

export function convertInputs(form, from, to) {
  for (const name of fields) {
    const input = form.elements.namedItem(name);
    if (!input) continue;
    if (!limits.has(input)) {
      limits.set(input, Object.fromEntries(['min', 'max'].map(attr => [attr,
        input.hasAttribute(attr) ? Number(input.getAttribute(attr)) * scale(from) : null])));
    }
    for (const [attr, mm] of Object.entries(limits.get(input))) {
      if (mm !== null) input.setAttribute(attr, String(mm / scale(to)));
    }
    input.step = 'any';
    if (input.value === '') continue;
    const mm = millimetres(input, from);
    if (!Number.isFinite(mm)) continue;
    input.value = String(Number((mm / scale(to)).toPrecision(15)));
    values.set(input, {mm, display: input.value});
  }
}

export function normalizeFormData(data, form, unit) {
  for (const name of fields) {
    const input = form.elements.namedItem(name);
    if (input && input.value !== '') data.set(name, String(millimetres(input, unit)));
  }
  return data;
}

export function displayLength(mm, unit) {
  return (mm / scale(unit)).toFixed(unit === 'in' ? 4 : 2);
}

export function fillStockInputs(form, stock, unit) {
  form.elements.namedItem('shape').value = stock.shape;
  for (const name of ['width', 'height', 'wall', 'corner_radius']) {
    const input = form.elements.namedItem(name);
    if (!input) continue;
    const mm = stock[name] ?? 0;
    input.value = String(Number((mm / scale(unit)).toPrecision(15)));
    values.set(input, {mm, display: input.value});
  }
}
