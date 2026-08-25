
const API_URL = "http://localhost:8000";

async function submitObservationToAPI(record){
  const response = await fetch(`${API_URL}/api/observations`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      project_id: record.project_id,
      site_id: record.site_id,
      project_name: record.project_name,
      record_type: record.record_type,
      observer: record.observer,
      observation_date: record.observation_date,
      latitude: record.latitude ? Number(record.latitude) : null,
      longitude: record.longitude ? Number(record.longitude) : null,
      notes: record.notes || "",
      payload: record
    })
  });

  if(!response.ok){
    throw new Error(await response.text());
  }

  return response.json();
}
