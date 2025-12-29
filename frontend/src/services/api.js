const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const API_TOKEN = import.meta.env.VITE_API_TOKEN || 'secret-token';

export const reportIssue = async (imageFile, lat, lng) => {
  const formData = new FormData();
  formData.append('file', imageFile);
  formData.append('latitude', lat.toString());
  formData.append('longitude', lng.toString());

  try {
    const response = await fetch(`${API_URL}/upload-issue`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${API_TOKEN}`, 
      },
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      console.error("❌ API Error Details:", errorData);
      throw new Error(`API Error: ${response.status} - ${JSON.stringify(errorData.detail || errorData)}`);
    }

    return await response.json();
  } catch (error) {
    console.error("Report failed:", error);
    throw error;
  }
};

export const resolveIssue = async (imageFile, issueId, engineerNotes = '') => {
  const formData = new FormData();
  formData.append('file', imageFile);
  formData.append('issue_id', issueId);
  formData.append('engineer_notes', engineerNotes);

  try {
    const response = await fetch(`${API_URL}/resolve-issue`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${API_TOKEN}`, 
      },
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      console.error("❌ Resolution API Error:", errorData);
      throw new Error(`API Error: ${response.status} - ${JSON.stringify(errorData.detail || errorData)}`);
    }

    return await response.json();
  } catch (error) {
    console.error("Resolution failed:", error);
    throw error;
  }
};
