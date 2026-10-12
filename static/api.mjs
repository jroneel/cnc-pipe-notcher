export async function readPlanResponse(response, exporting = false, stock = false) {
  const type = (response.headers.get('content-type') || '').split(';')[0].trim().toLowerCase();
  const jsonType = type === 'application/json' || type.endsWith('+json');
  if (!jsonType && !(response.ok && exporting && type === 'text/plain')) {
    throw new Error(`The server returned ${type || 'an unknown response type'} (HTTP ${response.status}) instead of ${exporting ? 'a G-code file' : 'JSON'}. The request may have reached a proxy or an incorrect API address. Check that the Python app is running and reopen its port page.`);
  }
  if (response.ok && exporting && type === 'text/plain') return response.blob();
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(`The API returned malformed JSON (HTTP ${response.status}). Check the application server logs.`);
  }
  if (!response.ok) throw new Error(typeof data?.error === 'string' ? data.error : `Request failed (HTTP ${response.status})`);
  if (stock) {
    if (!['round', 'square', 'rectangle'].includes(data?.shape) ||
        !['width', 'height', 'wall'].every(k => Number.isFinite(data[k]) && data[k] > 0)) {
      throw new Error('The API returned invalid tubing dimensions.');
    }
    if (data.corner_radius !== undefined && (!Number.isFinite(data.corner_radius) || data.corner_radius < 0)) {
      throw new Error('The API returned an invalid corner radius.');
    }
    return data;
  }
  if (exporting || !Array.isArray(data?.points) || data.points.length < 2 ||
      !data.points.every(p => ['x', 'y', 'z', 'a'].every(k => Number.isFinite(p[k]))) ||
      !['width', 'height', 'bevel', 'bevel_offset', 'triangles'].every(k => Number.isFinite(data[k])) ||
      !Array.isArray(data.warnings)) {
    throw new Error('The API returned an invalid toolpath response. Check the application server logs.');
  }
  return data;
}

export function planURL(pageURL, endpoint = 'plan') {
  const page = new URL(pageURL);
  // Keep a development proxy's mount prefix rather than posting to its host root.
  page.pathname = page.pathname.replace(/\/?$/, '/') + 'api/' + endpoint;
  page.search = '';
  page.hash = '';
  return page.href;
}
