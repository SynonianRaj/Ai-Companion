import { api } from "./api.js";

// Check if running directly as local file
if (window.location.protocol === "file:") {
  alert("⚠️ Notice: Please access AI Companion via http://127.0.0.1:8000 after running 'python app/main.py' in the backend directory, rather than opening index.html directly as a local file.");
}

// Application State
const state = {
  user: JSON.parse(localStorage.getItem("aanya_user") || "null"),
  relationship: JSON.parse(localStorage.getItem("aanya_rel") || "null"),
  persona: null,
  activeNotice: null
};

// Register Service Worker
if ("serviceWorker" in navigator && window.location.protocol.startsWith("http")) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("./public/sw.js").catch((err) => {
      console.log("ServiceWorker registration failed: ", err);
    });
  });
}

// DOM Elements
const chatFeed = document.getElementById("chat-feed");
const chatInput = document.getElementById("chat-input");
const sendBtn = document.getElementById("send-btn");
const settingsBtn = document.getElementById("settings-btn");
const devClockBtn = document.getElementById("dev-clock-btn");
const noticeBanner = document.getElementById("notice-banner");

// Modals
const onboardingModal = document.getElementById("onboarding-modal");
const settingsModal = document.getElementById("settings-modal");
const reportModal = document.getElementById("report-modal");
const devClockModal = document.getElementById("dev-clock-modal");

// Init Application
async function init() {
  try {
    state.persona = await api.getPersona();
    document.getElementById("persona-name").textContent = state.persona.name;
    document.getElementById("persona-bio").textContent = state.persona.bio;
  } catch (e) {
    console.error("Failed to load persona:", e);
  }

  if (!state.user || !state.relationship) {
    showOnboarding();
  } else {
    loadChatHistory();
    refreshRelationshipStatus();
  }
}

// Onboarding & Registration
function showOnboarding() {
  onboardingModal.style.display = "flex";
}

document.getElementById("onboarding-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = document.getElementById("onboard-username").value.trim();
  const ageConfirmed = document.getElementById("onboard-age").checked;
  const aiAccepted = document.getElementById("onboard-ai").checked;
  const errorEl = document.getElementById("onboard-error");
  errorEl.textContent = "";

  if (!ageConfirmed) {
    errorEl.textContent = "You must confirm you are 18+ to enter.";
    return;
  }
  if (!aiAccepted) {
    errorEl.textContent = "You must acknowledge the AI disclosure.";
    return;
  }

  try {
    const reg = await api.register(username, ageConfirmed, aiAccepted);
    state.user = { id: reg.user_id, username: reg.username };
    state.relationship = { id: reg.relationship_id };
    localStorage.setItem("aanya_user", JSON.stringify(state.user));
    localStorage.setItem("aanya_rel", JSON.stringify(state.relationship));

    onboardingModal.style.display = "none";
    loadChatHistory();
    refreshRelationshipStatus();
  } catch (err) {
    errorEl.textContent = err.message;
  }
});

// Load Chat History
async function loadChatHistory() {
  chatFeed.innerHTML = "";
  try {
    const messages = await api.getHistory(state.relationship.id);
    if (messages.length === 0) {
      // Prompt user with start suggestion
      appendMessage("assistant", (
        "Hey! Ek second... kya tumhara bhi oat milk iced latte tha? ☕ Wait, I think the barista " +
        "swapped our cups! Indiranagar cafes on a weekday afternoon are pure chaos, honestly. " +
        "I'm Aanya btw :)"
      ));
    } else {
      messages.forEach((msg) => {
        appendMessage(msg.role, msg.content, msg.metadata, msg.created_at);
      });
    }
  } catch (err) {
    console.error("Failed to load history:", err);
  }
}

// Append Message to Feed
function appendMessage(role, content, metadata = {}, timestamp = null) {
  const wrapper = document.createElement("div");
  wrapper.className = `message-wrapper ${role}`;

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.textContent = content;
  wrapper.appendChild(bubble);

  const meta = document.createElement("div");
  meta.className = "message-meta";
  const timeStr = timestamp ? new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "Just now";
  meta.innerHTML = `<span>${timeStr}</span>`;

  if (role === "assistant") {
    const reportBtn = document.createElement("button");
    reportBtn.className = "report-btn";
    reportBtn.textContent = "Report snippet";
    reportBtn.onclick = () => openReportModal(content);
    meta.appendChild(reportBtn);
  }

  wrapper.appendChild(meta);
  chatFeed.appendChild(wrapper);
  chatFeed.scrollTop = chatFeed.scrollHeight;
}

// Render Crisis Handoff Card
function renderCrisisCard(crisisHandoff) {
  const card = document.createElement("div");
  card.className = "crisis-handoff-card";

  let helplinesHtml = "";
  crisisHandoff.helpline_details.forEach((h) => {
    const telNumber = h.toll_free || h.number || "";
    const cleanTel = telNumber.split("/")[0].trim();
    helplinesHtml += `
      <div class="helpline-item">
        <div>
          <strong>${h.name}</strong><br>
          <span>${telNumber}</span>
        </div>
        ${cleanTel ? `<a href="tel:${cleanTel}" class="btn-call">Call</a>` : ""}
      </div>
    `;
  });

  card.innerHTML = `
    <div class="crisis-title">
      <span>🛡️ Immediate Support & Helpline Handoff</span>
    </div>
    <div class="crisis-text">${crisisHandoff.persona_text}</div>
    <div class="helpline-box">
      ${helplinesHtml}
    </div>
  `;

  chatFeed.appendChild(card);
  chatFeed.scrollTop = chatFeed.scrollHeight;
}

// Send Message Flow
async function handleSendMessage() {
  const text = chatInput.value.trim();
  if (!text) return;

  if (!state.user || !state.relationship || !state.relationship.id) {
    showOnboarding();
    return;
  }

  appendMessage("user", text);
  chatInput.value = "";
  sendBtn.disabled = true;

  // Typing indicator
  const typingEl = document.createElement("div");
  typingEl.className = "typing-indicator";
  typingEl.id = "typing-indicator";
  typingEl.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
  chatFeed.appendChild(typingEl);
  chatFeed.scrollTop = chatFeed.scrollHeight;

  try {
    const res = await api.sendMessage(state.relationship.id, text);
    typingEl.remove();

    if (res.crisis_handoff) {
      renderCrisisCard(res.crisis_handoff);
    } else {
      appendMessage("assistant", res.content);
    }

    refreshRelationshipStatus();
  } catch (err) {
    typingEl.remove();
    appendMessage("assistant", `[Notice: ${err.message}]`);
  } finally {
    sendBtn.disabled = false;
  }
}

sendBtn.addEventListener("click", handleSendMessage);
chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") handleSendMessage();
});

// Refresh Relationship & Memory Expiry Status
async function refreshRelationshipStatus() {
  if (!state.relationship) return;
  try {
    const settings = await api.getSettings(state.relationship.id);
    if (settings.is_entitled) {
      noticeBanner.style.display = "block";
      noticeBanner.textContent = "✨ Beta Pilot Entitlement Active: Memories are preserved during testing.";
    } else if (settings.days_until_expiry !== null) {
      noticeBanner.style.display = "block";
      noticeBanner.textContent = `⏳ Unsubscribed Status: Relationship memory expires in ${settings.days_until_expiry} days unless renewed.`;
    } else {
      noticeBanner.style.display = "none";
    }
  } catch (e) {
    console.warn("Could not fetch relationship status:", e);
  }
}

// Settings Modal & Memory Inspector
settingsBtn.addEventListener("click", async () => {
  if (!state.user || !state.relationship || !state.relationship.id) {
    showOnboarding();
    return;
  }
  settingsModal.style.display = "flex";
  loadSettingsView();
});

document.getElementById("close-settings-btn").addEventListener("click", () => {
  settingsModal.style.display = "none";
});

document.getElementById("reset-session-btn").addEventListener("click", () => {
  if (confirm("Reset current session and re-open 18+ onboarding?")) {
    localStorage.removeItem("aanya_user");
    localStorage.removeItem("aanya_rel");
    window.location.reload();
  }
});

async function loadSettingsView() {
  if (!state.relationship || !state.relationship.id) return;
  try {
    const settings = await api.getSettings(state.relationship.id);
    document.getElementById("realism-toggle").checked = settings.emotional_realism_enabled;
    document.getElementById("realism-intensity").value = settings.emotional_realism_intensity;

    // Load memories
    const memList = document.getElementById("memory-list");
    memList.innerHTML = "<p>Loading stored memories...</p>";
    const memories = await api.getMemories(state.relationship.id);
    if (memories.length === 0) {
      memList.innerHTML = "<p style='color: #94a3b8;'>No memories stored yet.</p>";
    } else {
      memList.innerHTML = "";
      memories.forEach((mem) => {
        const item = document.createElement("div");
        item.className = "memory-item";
        item.innerHTML = `
          <div>
            <strong>${mem.memory_type}:</strong> ${mem.content}
          </div>
          <button class="btn-delete-mem" data-id="${mem.id}">Delete</button>
        `;
        item.querySelector(".btn-delete-mem").onclick = async () => {
          await api.deleteMemory(state.relationship.id, mem.id);
          loadSettingsView();
        };
        memList.appendChild(item);
      });
    }
  } catch (err) {
    console.error("Failed to load settings:", err);
  }
}

document.getElementById("save-settings-btn").addEventListener("click", async () => {
  const enabled = document.getElementById("realism-toggle").checked;
  const intensity = document.getElementById("realism-intensity").value;
  await api.updateSettings(state.relationship.id, {
    emotional_realism_enabled: enabled,
    emotional_realism_intensity: intensity
  });
  settingsModal.style.display = "none";
});

// Report Snippet Modal
function openReportModal(snippetText) {
  reportModal.style.display = "flex";
  document.getElementById("report-snippet-preview").textContent = `"${snippetText}"`;
  document.getElementById("report-submit-btn").onclick = async () => {
    const category = document.getElementById("report-category").value;
    await api.submitReport(state.user.id, snippetText, category);
    reportModal.style.display = "none";
    alert("Report snippet submitted for quality review. Thank you!");
  };
}

document.getElementById("close-report-btn").addEventListener("click", () => {
  reportModal.style.display = "none";
});

// QA Dev Test Clock Controls
devClockBtn.addEventListener("click", () => {
  devClockModal.style.display = "flex";
});

document.getElementById("close-dev-clock-btn").addEventListener("click", () => {
  devClockModal.style.display = "none";
});

document.getElementById("advance-12-days-btn").addEventListener("click", async () => {
  const res = await api.advanceClock(12);
  alert(`Virtual time advanced by 12 days!\nVirtual Now: ${res.virtual_now}`);
  refreshRelationshipStatus();
});

document.getElementById("advance-15-days-btn").addEventListener("click", async () => {
  const res = await api.advanceClock(3);
  alert(`Virtual time advanced to Day 15!\nLifecycle events: ${JSON.stringify(res.lifecycle_events)}`);
  refreshRelationshipStatus();
});

document.getElementById("reset-clock-btn").addEventListener("click", async () => {
  await api.resetClock();
  alert("Clock reset to system time.");
  refreshRelationshipStatus();
});

// Start App
init();
