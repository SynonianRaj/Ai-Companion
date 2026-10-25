const API_BASE = "/api";

export const api = {
  async register(username, ageConfirmed, aiAccepted, city = null) {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username,
        age_confirmed: ageConfirmed,
        ai_disclosure_accepted: aiAccepted,
        city: city && city.trim() ? city.trim() : null
      })
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Registration failed");
    }
    return res.json();
  },

  async getPersona() {
    const res = await fetch(`${API_BASE}/persona`);
    if (!res.ok) throw new Error("Failed to load persona");
    return res.json();
  },

  async sendMessage(relationshipId, options) {
    // Options can be a string (legacy) or an object
    const payload = { relationship_id: relationshipId };
    if (typeof options === "string") {
      payload.message = options;
      payload.pacing_mode = "realistic";
    } else {
      if (options.messages && Array.isArray(options.messages)) {
        payload.messages = options.messages;
      } else if (options.message) {
        payload.message = options.message;
      }
      payload.pacing_mode = options.pacingMode || "realistic";
      if (options.clientMsgId) payload.client_msg_id = options.clientMsgId;
    }

    const res = await fetch(`${API_BASE}/chat/send`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to send message");
    }
    return res.json();
  },

  async skipWait(relationshipId) {
    const res = await fetch(`${API_BASE}/chat/skip-wait`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ relationship_id: relationshipId })
    });
    if (!res.ok) throw new Error("Failed to skip wait");
    return res.json();
  },

  async getHistory(relationshipId) {
    const res = await fetch(`${API_BASE}/chat/history?relationship_id=${relationshipId}`);
    if (!res.ok) throw new Error("Failed to load chat history");
    return res.json();
  },

  async getMemories(relationshipId) {
    const res = await fetch(`${API_BASE}/memories?relationship_id=${relationshipId}`);
    if (!res.ok) throw new Error("Failed to load memories");
    return res.json();
  },

  async deleteMemory(relationshipId, memoryId) {
    const res = await fetch(`${API_BASE}/memories/${memoryId}?relationship_id=${relationshipId}`, {
      method: "DELETE"
    });
    if (!res.ok) throw new Error("Failed to delete memory");
    return res.json();
  },

  async submitReport(userId, snippet, category = "quality_review") {
    const res = await fetch(`${API_BASE}/report?user_id=${userId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        snippet,
        consent_given: true,
        category
      })
    });
    if (!res.ok) throw new Error("Failed to submit report");
    return res.json();
  },

  async getSettings(relationshipId) {
    const res = await fetch(`${API_BASE}/settings/relationship?relationship_id=${relationshipId}`);
    if (!res.ok) throw new Error("Failed to fetch settings");
    return res.json();
  },

  async updateSettings(relationshipId, payload) {
    const res = await fetch(`${API_BASE}/settings/relationship?relationship_id=${relationshipId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error("Failed to update settings");
    return res.json();
  },

  async advanceClock(days) {
    const res = await fetch(`${API_BASE}/dev/clock/advance`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ days })
    });
    if (!res.ok) throw new Error("Failed to advance test clock");
    return res.json();
  },

  async resetClock() {
    const res = await fetch(`${API_BASE}/dev/clock/reset`, {
      method: "POST"
    });
    if (!res.ok) throw new Error("Failed to reset clock");
    return res.json();
  },

  async sendPresencePing(relationshipId) {
    if (!relationshipId) return;
    try {
      await fetch(`${API_BASE}/presence/ping?relationship_id=${encodeURIComponent(relationshipId)}`, {
        method: "POST"
      });
    } catch (e) {
      // Non-critical background ping
    }
  },

  async getVapidKey() {
    const res = await fetch(`${API_BASE}/push/vapid-public-key`);
    if (!res.ok) return null;
    const data = await res.json();
    return data.public_key;
  },

  async subscribePush(relationshipId, endpoint, p256dh, auth) {
    const res = await fetch(`${API_BASE}/push/subscribe`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        relationship_id: relationshipId,
        endpoint,
        p256dh,
        auth
      })
    });
    if (!res.ok) throw new Error("Failed to subscribe for push");
    return res.json();
  }
};
