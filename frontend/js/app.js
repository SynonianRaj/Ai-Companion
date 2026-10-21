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
  activeNotice: null,
  pacingMode: localStorage.getItem("aanya_pacing_mode") || "realistic",
  userBurstQueue: [],
  burstDebounceTimer: null,
  burstMaxTimeout: null,
  pendingDeliveryTimer: null,
  activeChunkTimeouts: []
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
const skipWaitBtn = document.getElementById("skip-wait-btn");
const noticeBanner = document.getElementById("notice-banner");
const personaStatusText = document.getElementById("persona-status-text");

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
    updatePersonaStatus("Online");
  } catch (e) {
    console.error("Failed to load persona:", e);
  }

  if (!state.user || !state.relationship || !state.relationship.id) {
    showOnboarding();
  } else {
    try {
      await refreshRelationshipStatus();
      await loadChatHistory();
    } catch (err) {
      if (err.message && err.message.includes("Relationship not found")) {
        resetSessionToOnboarding("Previous session expired or was reset. Please start a new conversation.");
      }
    }
  }
}

function resetSessionToOnboarding(noticeMessage = null) {
  localStorage.removeItem("aanya_user");
  localStorage.removeItem("aanya_rel");
  state.user = null;
  state.relationship = null;
  chatFeed.innerHTML = "";
  if (noticeMessage) {
    const errorEl = document.getElementById("onboard-error");
    if (errorEl) errorEl.textContent = noticeMessage;
  }
  showOnboarding();
}

function updatePersonaStatus(status, isTyping = false) {
  if (personaStatusText) {
    personaStatusText.textContent = status;
    if (isTyping) {
      personaStatusText.classList.add("typing");
    } else {
      personaStatusText.classList.remove("typing");
    }
  }
}

// Onboarding & Registration
function showOnboarding() {
  onboardingModal.style.display = "flex";
}

document.getElementById("onboarding-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = document.getElementById("onboard-username").value.trim();
  const cityInput = document.getElementById("onboard-city");
  const city = cityInput ? cityInput.value.trim() : null;
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
    const reg = await api.register(username, ageConfirmed, aiAccepted, city);
    state.user = { id: reg.user_id, username: reg.username, city: reg.city };
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
  if (state.pendingDeliveryTimer) {
    clearTimeout(state.pendingDeliveryTimer);
    state.pendingDeliveryTimer = null;
  }

  try {
    const res = await api.getHistory(state.relationship.id);
    const messages = res.messages || (Array.isArray(res) ? res : []);

    chatFeed.innerHTML = "";

    if (messages.length === 0) {
      // Opening Turn: trigger grounded stranger opener
      appendInitialIcebreaker();
    } else {
      let lastRole = null;
      messages.forEach((msg) => {
        const isFollowup = (msg.role === lastRole);
        appendMessageElement(msg.role, msg.content, {
          timestamp: msg.created_at,
          seenAt: msg.seen_at,
          status: msg.status,
          isFollowup
        });
        lastRole = msg.role;
      });
    }

    if (res.persona_activity) {
      updatePersonaStatus(res.persona_activity);
    }

    // If there are pending un-delivered chunks, schedule auto-delivery
    if (res.pending_delivery && res.next_deliver_at) {
      const waitMs = Math.max(300, new Date(res.next_deliver_at) - Date.now());
      if (state.pacingMode !== "turbo") {
        showSkipWaitButton();
      }
      showTypingIndicator();
      state.pendingDeliveryTimer = setTimeout(() => {
        removeTypingIndicator();
        loadChatHistory();
      }, waitMs);
    } else {
      hideSkipWaitButton();
    }
  } catch (err) {
    console.error("Failed to load history:", err);
    if (err.message && err.message.includes("Relationship not found")) {
      resetSessionToOnboarding("Previous session expired or was reset. Please start a new conversation.");
    }
  }
}

function appendInitialIcebreaker() {
  const cleanName = state.user && state.user.username ? state.user.username : "there";
  const city = state.user && state.user.city ? state.user.city : null;

  const chunks = [
    `Hey ${cleanName}! Nice to connect with you :)`,
    "I'm Aanya btw. Was just taking a quick breather from work with some chai ☕"
  ];
  if (city) {
    chunks.push(`Aanya from Bangalore here. ${city} se ho na tum? Tell me a bit about what it's like living there!`);
  } else {
    chunks.push("Pehle yeh batao, which city are you texting from? Tell me a bit about yourself!");
  }

  chunks.forEach((c, idx) => {
    appendMessageElement("assistant", c, { isFollowup: idx > 0 });
  });
}

// Append Message to Feed
function appendMessageElement(role, content, options = {}) {
  const { timestamp, seenAt, isFollowup, status } = options;

  const wrapper = document.createElement("div");
  wrapper.className = `message-wrapper ${role}`;
  if (isFollowup) {
    wrapper.classList.add("grouped-followup");
  }

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.textContent = content;
  wrapper.appendChild(bubble);

  const meta = document.createElement("div");
  meta.className = "message-meta";
  const timeStr = timestamp ? new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "Just now";
  
  let receiptHtml = "";
  if (role === "user") {
    // Receipts: ✓ (Sent), ✓✓ (Delivered), ✓✓ blue (Seen)
    if (status === "sent") {
      receiptHtml = '<span class="receipt-tick" title="Sent">✓</span>';
    } else if (seenAt && new Date(seenAt) <= new Date()) {
      receiptHtml = '<span class="receipt-tick seen" title="Read">✓✓</span>';
    } else {
      receiptHtml = '<span class="receipt-tick" title="Delivered">✓✓</span>';
    }
  }

  meta.innerHTML = `<span>${timeStr}</span>${receiptHtml}`;

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

  return wrapper;
}

// Typing Indicator Helpers
function showTypingIndicator() {
  let typingEl = document.getElementById("typing-indicator");
  if (!typingEl) {
    typingEl = document.createElement("div");
    typingEl.className = "typing-indicator";
    typingEl.id = "typing-indicator";
    typingEl.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
    chatFeed.appendChild(typingEl);
    chatFeed.scrollTop = chatFeed.scrollHeight;
  }
  updatePersonaStatus("typing...", true);
}

function removeTypingIndicator() {
  const typingEl = document.getElementById("typing-indicator");
  if (typingEl) typingEl.remove();
}

// Skip Wait Button Helpers
function showSkipWaitButton() {
  if (skipWaitBtn) skipWaitBtn.style.display = "flex";
}

function hideSkipWaitButton() {
  if (skipWaitBtn) skipWaitBtn.style.display = "none";
}

if (skipWaitBtn) {
  skipWaitBtn.addEventListener("click", async () => {
    hideSkipWaitButton();
    removeTypingIndicator();
    clearActiveChunkTimeouts();
    try {
      await api.skipWait(state.relationship.id);
      await loadChatHistory();
    } catch (e) {
      console.warn("Skip wait failed:", e);
    }
  });
}

function clearActiveChunkTimeouts() {
  state.activeChunkTimeouts.forEach(t => clearTimeout(t));
  state.activeChunkTimeouts = [];
}

// Render Crisis Handoff Card
function renderCrisisCard(crisisHandoff) {
  hideSkipWaitButton();
  removeTypingIndicator();
  updatePersonaStatus("Immediate Support");

  const card = document.createElement("div");
  card.className = "crisis-handoff-card";

  let helplinesHtml = "";
  (crisisHandoff.helpline_details || []).forEach((h) => {
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

// User Burst Debouncer
function handleUserMessageInput() {
  const text = chatInput.value.trim();
  if (!text) return;

  if (!state.user || !state.relationship || !state.relationship.id) {
    showOnboarding();
    return;
  }

  // Clear input immediately, keeping send button enabled!
  chatInput.value = "";

  // Render user bubble immediately with Sent status (✓)
  const isFollowup = state.userBurstQueue.length > 0;
  const wrapperEl = appendMessageElement("user", text, {
    status: "sent",
    isFollowup
  });

  const clientMsgId = "msg_" + Date.now() + "_" + Math.random().toString(36).substring(2, 8);
  state.userBurstQueue.push({
    text,
    element: wrapperEl,
    clientMsgId
  });

  // Reset Debounce Timer (3 seconds)
  if (state.burstDebounceTimer) clearTimeout(state.burstDebounceTimer);
  state.burstDebounceTimer = setTimeout(flushUserBurst, 3000);

  // Hard Cap Timer (8 seconds total)
  if (!state.burstMaxTimeout) {
    state.burstMaxTimeout = setTimeout(flushUserBurst, 8000);
  }
}

// Flush Burst on Page Unload to ensure zero message loss
window.addEventListener("beforeunload", () => {
  if (state.userBurstQueue.length > 0) {
    flushUserBurst();
  }
});

// Flush Queued User Burst to Server
async function flushUserBurst() {
  if (state.burstDebounceTimer) {
    clearTimeout(state.burstDebounceTimer);
    state.burstDebounceTimer = null;
  }
  if (state.burstMaxTimeout) {
    clearTimeout(state.burstMaxTimeout);
    state.burstMaxTimeout = null;
  }

  if (state.userBurstQueue.length === 0) return;

  const currentBurst = [...state.userBurstQueue];
  state.userBurstQueue = [];

  // Update checkmarks on current burst to Delivered (✓✓)
  currentBurst.forEach(item => {
    const tick = item.element.querySelector(".receipt-tick");
    if (tick) tick.textContent = "✓✓";
  });

  const messagesList = currentBurst.map(b => b.text);
  const primaryClientMsgId = currentBurst[0].clientMsgId;

  try {
    const res = await api.sendMessage(state.relationship.id, {
      messages: messagesList,
      pacingMode: state.pacingMode,
      clientMsgId: primaryClientMsgId
    });

    if (res.crisis_handoff) {
      renderCrisisCard(res.crisis_handoff);
      return;
    }

    if (res.persona_activity) {
      updatePersonaStatus(res.persona_activity);
    }

    // Schedule blue ticks (Seen ✓✓)
    const seenDelay = Math.max(0, new Date(res.seen_at) - Date.now());
    setTimeout(() => {
      currentBurst.forEach(item => {
        const tick = item.element.querySelector(".receipt-tick");
        if (tick) {
          tick.textContent = "✓✓";
          tick.classList.add("seen");
        }
      });
      updatePersonaStatus("Online");
    }, seenDelay);

    // Show Skip Wait button if realistic delay
    if (res.delay_tier !== "quick" && state.pacingMode !== "turbo") {
      showSkipWaitButton();
    }

    // Schedule progressive chunk rendering strictly from deliver_at
    scheduleChunkDeliveries(res.chunk_details || [], currentBurst);

    refreshRelationshipStatus();
  } catch (err) {
    removeTypingIndicator();
    hideSkipWaitButton();
    if (err.message && err.message.includes("Relationship not found")) {
      resetSessionToOnboarding("Your previous session was reset or expired. Please re-enter your name to continue.");
    } else {
      appendMessageElement("assistant", `[Notice: ${err.message}]`);
    }
  }
}

function scheduleChunkDeliveries(chunkDetails, userBurst) {
  clearActiveChunkTimeouts();

  chunkDetails.forEach((chunk, idx) => {
    const deliverTime = new Date(chunk.deliver_at).getTime();
    const now = Date.now();
    const waitMs = Math.max(0, deliverTime - now);
    const typingDurationMs = Math.round((chunk.typing_duration_seconds || 1.5) * 1000);
    const typingStartMs = Math.max(0, waitMs - typingDurationMs);

    // Schedule typing bubble right before delivery
    const tTyping = setTimeout(() => {
      showTypingIndicator();
    }, typingStartMs);
    state.activeChunkTimeouts.push(tTyping);

    // Schedule chunk bubble delivery
    const tDeliver = setTimeout(() => {
      removeTypingIndicator();
      appendMessageElement("assistant", chunk.content, {
        timestamp: chunk.deliver_at,
        isFollowup: idx > 0
      });

      if (idx === chunkDetails.length - 1) {
        hideSkipWaitButton();
        updatePersonaStatus("Online");
      }
    }, waitMs);
    state.activeChunkTimeouts.push(tDeliver);
  });
}

sendBtn.addEventListener("click", handleUserMessageInput);
chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") handleUserMessageInput();
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
    if (e.message && e.message.includes("Relationship not found")) {
      resetSessionToOnboarding("Previous session expired or was reset. Please start a new conversation.");
    } else {
      console.warn("Could not fetch relationship status:", e);
    }
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

    const pacingSelect = document.getElementById("pacing-mode-select");
    if (pacingSelect) {
      pacingSelect.value = state.pacingMode;
    }

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
  const pacingSelect = document.getElementById("pacing-mode-select");
  if (pacingSelect) {
    state.pacingMode = pacingSelect.value;
    localStorage.setItem("aanya_pacing_mode", state.pacingMode);
  }

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
