import { api } from "./api.js?v=9.4";

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
  activeChunkTimeouts: [],
  renderedMsgIds: new Set(),
  pendingChunkIds: new Set(),
  lastRenderedDateKey: null
};

// Register Service Worker
if ("serviceWorker" in navigator && window.location.protocol.startsWith("http")) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("./public/sw.js?v=11.0").catch((err) => {
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
const installPwaBtn = document.getElementById("install-pwa-btn");
const noticeBanner = document.getElementById("notice-banner");
const personaStatusText = document.getElementById("persona-status-text");

// PWA Install Handling
let deferredInstallPrompt = null;
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  deferredInstallPrompt = e;
  if (installPwaBtn) {
    installPwaBtn.style.display = "inline-flex";
  }
});

if (installPwaBtn) {
  // Check if already in standalone display mode
  const isStandalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
  if (!isStandalone) {
    // Show install button for mobile devices by default
    const isMobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
    if (isMobile) {
      installPwaBtn.style.display = "inline-flex";
    }
  }

  installPwaBtn.addEventListener("click", async () => {
    if (deferredInstallPrompt) {
      deferredInstallPrompt.prompt();
      const { outcome } = await deferredInstallPrompt.userChoice;
      if (outcome === "accepted") {
        installPwaBtn.style.display = "none";
      }
      deferredInstallPrompt = null;
    } else {
      const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
      if (isIOS) {
        alert("To install Aanya on your iPhone:\n1. Tap the Share button (⎋ box with arrow) at the bottom of Safari.\n2. Scroll down and tap 'Add to Home Screen' (⊞).");
      } else {
        alert("To install Aanya:\nTap your browser's menu (three dots ⋮) at the top right and tap 'Install app' or 'Add to Home screen'.");
      }
    }
  });
}

window.addEventListener("appinstalled", () => {
  deferredInstallPrompt = null;
  if (installPwaBtn) {
    installPwaBtn.style.display = "none";
  }
});

// Mobile Dynamic Viewport & Virtual Keyboard Handler
if (window.visualViewport) {
  const onViewportResize = () => {
    const container = document.getElementById("app-container");
    if (container && window.innerWidth <= 600) {
      container.style.height = `${window.visualViewport.height}px`;
      if (chatFeed) {
        chatFeed.scrollTop = chatFeed.scrollHeight;
      }
    }
  };
  window.visualViewport.addEventListener("resize", onViewportResize);
  window.visualViewport.addEventListener("scroll", onViewportResize);
}

if (chatInput) {
  chatInput.addEventListener("focus", () => {
    setTimeout(() => {
      if (chatFeed) chatFeed.scrollTop = chatFeed.scrollHeight;
    }, 300);
  });
}

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

const statusDot = document.querySelector(".avatar .status-dot");
const personaBio = document.getElementById("persona-bio");

function applyPersonaPresence(presence) {
  if (!presence) return;
  const statusLabel = presence.status_text || "online";
  const cityLabel = presence.city_label || "Indiranagar, Bengaluru";

  const statusSpan = document.getElementById("persona-status-text");
  if (statusSpan) {
    statusSpan.textContent = statusLabel;
  }

  if (statusDot) {
    if (presence.is_online) {
      statusDot.className = "status-dot online";
    } else {
      statusDot.className = "status-dot offline";
    }
  }
}

function updatePersonaStatus(status, isTyping = false) {
  const statusSpan = document.getElementById("persona-status-text");
  if (statusSpan) {
    statusSpan.textContent = status;
    if (isTyping) {
      statusSpan.classList.add("typing");
    } else {
      statusSpan.classList.remove("typing");
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

// Canonical Date Key: YYYY-MM-DD
function getLocalDateKey(dateInput) {
  const d = new Date(dateInput || Date.now());
  if (isNaN(d.getTime())) return "";
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

// WhatsApp Relative Date Label: Today, Yesterday, or D MMMM YYYY
function getRelativeDateLabel(dateKey) {
  if (!dateKey) return "Today";
  const now = new Date();
  const todayKey = getLocalDateKey(now);
  const yesterday = new Date(now.getTime() - 86400000);
  const yesterdayKey = getLocalDateKey(yesterday);

  if (dateKey === todayKey) return "Today";
  if (dateKey === yesterdayKey) return "Yesterday";

  const parts = dateKey.split("-");
  if (parts.length === 3) {
    const y = parseInt(parts[0], 10);
    const m = parseInt(parts[1], 10);
    const d = parseInt(parts[2], 10);
    const dateObj = new Date(y, m - 1, d);
    const options = { day: "numeric", month: "long" };
    if (y !== now.getFullYear()) {
      options.year = "numeric";
    }
    return dateObj.toLocaleDateString(undefined, options);
  }
  return dateKey;
}

// Render Date Separator Bubble into Chat Feed
function renderDateSeparatorIfNeeded(dateInput) {
  const dateKey = getLocalDateKey(dateInput);
  if (!dateKey) return;
  if (dateKey !== state.lastRenderedDateKey) {
    const sep = document.createElement("div");
    sep.className = "chat-date-separator";
    sep.setAttribute("data-date-key", dateKey);
    sep.innerHTML = `<span class="chat-date-bubble">${getRelativeDateLabel(dateKey)}</span>`;
    chatFeed.appendChild(sep);
    state.lastRenderedDateKey = dateKey;
  }
}

// Relative Message Time: Under 1m -> "Just now", else 12-hour formatted time (e.g. 12:47 AM)
function formatMessageTime(timestamp) {
  if (!timestamp) return "Just now";
  const d = new Date(timestamp);
  if (isNaN(d.getTime())) return "Just now";
  const diffMs = Date.now() - d.getTime();
  if (diffMs < 60000 && diffMs >= -5000) {
    return "Just now";
  }
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", hour12: true });
}

// Load Chat History
async function loadChatHistory() {
  clearActiveChunkTimeouts();
  if (state.pendingDeliveryTimer) {
    clearTimeout(state.pendingDeliveryTimer);
    state.pendingDeliveryTimer = null;
  }

  try {
    const res = await api.getHistory(state.relationship.id);
    const messages = res.messages || (Array.isArray(res) ? res : []);

    chatFeed.innerHTML = "";
    state.renderedMsgIds.clear();
    state.pendingChunkIds.clear();
    state.lastRenderedDateKey = null;

    if (messages.length === 0) {
      // Opening Turn: trigger grounded stranger opener
      appendInitialIcebreaker();
      knownMessageCount = 0;
    } else {
      // Canonical chronological sort: deliver_at (or created_at), tie-broken by sequence_order, then id
      messages.sort((a, b) => {
        const timeA = new Date(a.deliver_at || a.created_at).getTime();
        const timeB = new Date(b.deliver_at || b.created_at).getTime();
        if (timeA !== timeB) return timeA - timeB;
        if ((a.sequence_order || 0) !== (b.sequence_order || 0)) {
          return (a.sequence_order || 0) - (b.sequence_order || 0);
        }
        return (a.id || "").localeCompare(b.id || "");
      });

      let lastRole = null;
      messages.forEach((msg) => {
        const isFollowup = (msg.role === lastRole);
        appendMessageElement(msg.role, msg.content, {
          id: msg.id,
          timestamp: msg.deliver_at || msg.created_at,
          seenAt: msg.seen_at,
          status: msg.status,
          isFollowup
        });
        lastRole = msg.role;
      });
      knownMessageCount = messages.length;
    }

    if (res.presence) {
      applyPersonaPresence(res.presence);
    } else if (res.persona_activity) {
      updatePersonaStatus(res.persona_activity);
    }

    // If there are pending un-delivered chunks, schedule auto-delivery
    if (res.pending_delivery && res.next_deliver_at) {
      const waitMs = Math.max(300, new Date(res.next_deliver_at) - Date.now());
      if (res.show_skip_wait && state.pacingMode !== "turbo") {
        showSkipWaitButton();
      } else {
        hideSkipWaitButton();
      }
      // Typing indicator only when delivery is imminent (<= 2500ms)
      if (waitMs <= 2500) {
        showTypingIndicator();
      } else {
        removeTypingIndicator();
        const tTyping = setTimeout(() => {
          showTypingIndicator();
        }, Math.max(0, waitMs - 2000));
        state.activeChunkTimeouts.push(tTyping);
      }
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

  const nowIso = new Date().toISOString();
  chunks.forEach((c, idx) => {
    appendMessageElement("assistant", c, {
      id: `icebreaker_${idx}`,
      timestamp: nowIso,
      isFollowup: idx > 0
    });
  });
}

// Append Message to Feed
function appendMessageElement(role, content, options = {}) {
  const { id, clientMsgId, timestamp, seenAt, isFollowup, status } = options;

  // Deduplication guard: Never append a duplicate message with the same database ID
  if (id && state.renderedMsgIds.has(id)) {
    const existing = document.querySelector(`[data-msg-id="${id}"]`);
    if (existing) return existing;
  }

  // Ensure WhatsApp-style date separator is rendered if calendar day changed
  const msgTimestamp = timestamp || new Date().toISOString();
  renderDateSeparatorIfNeeded(msgTimestamp);

  const wrapper = document.createElement("div");
  wrapper.className = `message-wrapper ${role}`;
  if (isFollowup) {
    wrapper.classList.add("grouped-followup");
  }
  if (id) {
    wrapper.setAttribute("data-msg-id", id);
    state.renderedMsgIds.add(id);
  }
  if (clientMsgId) {
    wrapper.setAttribute("data-client-id", clientMsgId);
  }

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.textContent = content;
  wrapper.appendChild(bubble);

  const meta = document.createElement("div");
  meta.className = "message-meta";
  const timeStr = formatMessageTime(msgTimestamp);

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

  meta.innerHTML = `<span class="message-time" data-timestamp="${msgTimestamp}">${timeStr}</span>${receiptHtml}`;

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
  const nowIso = new Date().toISOString();
  const clientMsgId = "msg_" + Date.now() + "_" + Math.random().toString(36).substring(2, 8);
  const wrapperEl = appendMessageElement("user", text, {
    clientMsgId,
    timestamp: nowIso,
    status: "sent",
    isFollowup
  });

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
  clearActiveChunkTimeouts();

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

    if (res.presence) {
      applyPersonaPresence(res.presence);
    } else if (res.persona_activity) {
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
      // If response presence indicates online, keep online
      if (res.presence && res.presence.is_online) {
        updatePersonaStatus("online");
        if (statusDot) statusDot.className = "status-dot online";
      }
    }, seenDelay);

    // Show Skip Wait button only if backend authoritatively signals it
    if (res.show_skip_wait && state.pacingMode !== "turbo") {
      showSkipWaitButton();
    } else {
      hideSkipWaitButton();
    }

    // Register pending chunk IDs to avoid polling collisions
    const chunks = res.chunk_details || [];
    chunks.forEach(c => {
      if (c.id) state.pendingChunkIds.add(c.id);
    });
    knownMessageCount += currentBurst.length + chunks.length;

    // Schedule progressive chunk rendering strictly from deliver_at
    scheduleChunkDeliveries(chunks, currentBurst);

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
  if (!chunkDetails || chunkDetails.length === 0) {
    removeTypingIndicator();
    hideSkipWaitButton();
    return;
  }

  // Deduplicate chunks within the response payload itself as a frontend safeguard
  const seenTexts = new Set();
  const uniqueChunks = [];
  for (const c of chunkDetails) {
    const trimmed = (c.content || "").trim();
    if (!trimmed || seenTexts.has(trimmed)) continue;
    seenTexts.add(trimmed);
    uniqueChunks.push(c);
  }

  uniqueChunks.forEach((chunk, idx) => {
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
      if (chunk.id) {
        state.pendingChunkIds.delete(chunk.id);
      }
      // Deduplication safeguard: if already rendered by loadChatHistory/polling, skip duplicate append!
      if (!chunk.id || !state.renderedMsgIds.has(chunk.id)) {
        appendMessageElement("assistant", chunk.content, {
          id: chunk.id,
          timestamp: chunk.deliver_at,
          isFollowup: idx > 0
        });
      }

      if (idx === uniqueChunks.length - 1) {
        hideSkipWaitButton();
        applyPersonaPresence({ is_online: true, status_text: "online", subtitle: "online" });
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
  refreshNotificationSettingsUI();
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

// Settings Modal Push Notification Handlers
const pushStatusBadge = document.getElementById("push-status-badge");
const settingsEnablePushBtn = document.getElementById("settings-enable-push-btn");
const settingsTestPushBtn = document.getElementById("settings-test-push-btn");
const settingsPushFeedback = document.getElementById("settings-push-feedback");

function refreshNotificationSettingsUI() {
  if (!("Notification" in window)) {
    if (pushStatusBadge) {
      pushStatusBadge.textContent = "Not Supported";
      pushStatusBadge.className = "badge-status badge-gray";
    }
    if (settingsEnablePushBtn) settingsEnablePushBtn.style.display = "none";
    if (settingsTestPushBtn) settingsTestPushBtn.style.display = "none";
    return;
  }

  const perm = Notification.permission;
  if (perm === "granted") {
    if (pushStatusBadge) {
      pushStatusBadge.textContent = "Enabled";
      pushStatusBadge.className = "badge-status badge-green";
    }
    if (settingsEnablePushBtn) settingsEnablePushBtn.style.display = "none";
    if (settingsTestPushBtn) settingsTestPushBtn.style.display = "inline-flex";
  } else if (perm === "denied") {
    if (pushStatusBadge) {
      pushStatusBadge.textContent = "Blocked";
      pushStatusBadge.className = "badge-status badge-red";
    }
    if (settingsEnablePushBtn) settingsEnablePushBtn.style.display = "none";
    if (settingsTestPushBtn) settingsTestPushBtn.style.display = "none";
    if (settingsPushFeedback) settingsPushFeedback.textContent = "Notifications are blocked in your browser site settings.";
  } else {
    // default
    if (pushStatusBadge) {
      pushStatusBadge.textContent = "Not Enabled";
      pushStatusBadge.className = "badge-status badge-gray";
    }
    if (settingsEnablePushBtn) settingsEnablePushBtn.style.display = "inline-flex";
    if (settingsTestPushBtn) settingsTestPushBtn.style.display = "none";
  }
}

if (settingsEnablePushBtn) {
  settingsEnablePushBtn.addEventListener("click", async () => {
    if (settingsPushFeedback) settingsPushFeedback.textContent = "Requesting permission...";
    try {
      const perm = await Notification.requestPermission();
      if (perm === "granted") {
        await subscribeToWebPush();
        refreshNotificationSettingsUI();
        if (settingsPushFeedback) settingsPushFeedback.textContent = "Push notifications enabled successfully!";
      } else if (perm === "denied") {
        refreshNotificationSettingsUI();
        if (settingsPushFeedback) settingsPushFeedback.textContent = "Notifications were blocked in browser settings.";
      } else {
        refreshNotificationSettingsUI();
      }
    } catch (e) {
      if (settingsPushFeedback) settingsPushFeedback.textContent = `Error: ${e.message}`;
    }
  });
}

if (settingsTestPushBtn) {
  settingsTestPushBtn.addEventListener("click", async () => {
    if (!state.relationship || !state.relationship.id) return;
    if (settingsPushFeedback) settingsPushFeedback.textContent = "Dispatching test push...";
    try {
      const res = await api.testPush(state.relationship.id);
      if (settingsPushFeedback) settingsPushFeedback.textContent = res.message || "Test push sent!";
    } catch (e) {
      if (settingsPushFeedback) settingsPushFeedback.textContent = `Test push failed: ${e.message}`;
    }
  });
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/\-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

async function subscribeToWebPush() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;
  try {
    const reg = await navigator.serviceWorker.ready;
    const vapidKey = await api.getVapidKey();
    if (!vapidKey) return;
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(vapidKey)
    });
    const subJson = sub.toJSON();
    if (subJson && subJson.keys && state.relationship && state.relationship.id) {
      await api.subscribePush(
        state.relationship.id,
        sub.endpoint,
        subJson.keys.p256dh,
        subJson.keys.auth
      );
      console.log("Web Push subscription registered successfully");
    }
  } catch (err) {
    console.warn("Web Push registration error:", err);
  }
}

// Periodic presence ping (every 25s) so backend knows user is currently looking at app
setInterval(() => {
  if (state.relationship && state.relationship.id && document.visibilityState === "visible") {
    api.sendPresencePing(state.relationship.id);
  }
}, 25000);

window.addEventListener("focus", () => {
  if (state.relationship && state.relationship.id) {
    api.sendPresencePing(state.relationship.id);
    checkForNewMessages();
  }
});

let knownMessageCount = 0;
async function checkForNewMessages() {
  if (!state.relationship || !state.relationship.id) return;
  try {
    const res = await api.getHistory(state.relationship.id);
    const msgs = res.messages || (Array.isArray(res) ? res : []);

    // Filter out messages already rendered in DOM or pending in active chunk delivery
    const unrenderedMsgs = msgs.filter(m =>
      !state.renderedMsgIds.has(m.id) && !state.pendingChunkIds.has(m.id)
    );

    if (unrenderedMsgs.length > 0) {
      unrenderedMsgs.forEach(m => {
        if (m.role === "assistant") {
          showTypingIndicator();
          setTimeout(() => {
            removeTypingIndicator();
            appendMessageElement("assistant", m.content, {
              id: m.id,
              timestamp: m.deliver_at || m.created_at
            });
            updatePersonaStatus("Online");
          }, 800);
        } else if (m.role === "user") {
          appendMessageElement("user", m.content, {
            id: m.id,
            timestamp: m.deliver_at || m.created_at,
            status: m.status
          });
        }
      });
    }
    knownMessageCount = msgs.length;
  } catch (e) {
    // Non-critical background check
  }
}

// Live message polling for online users (every 4s)
setInterval(() => {
  if (document.visibilityState === "visible" && state.relationship && state.relationship.id && state.userBurstQueue.length === 0) {
    checkForNewMessages();
  }
}, 4000);

// 15-second timer for relative timestamps ("Just now" -> exact time) and midnight transitions
setInterval(() => {
  // 1. Upgrade "Just now" to exact time once 60s has passed
  const timeSpans = document.querySelectorAll(".message-time[data-timestamp]");
  timeSpans.forEach(span => {
    const ts = span.getAttribute("data-timestamp");
    if (ts) {
      const formatted = formatMessageTime(ts);
      if (span.textContent !== formatted) {
        span.textContent = formatted;
      }
    }
  });

  // 2. Midnight transition for date separators
  const dateSeparators = document.querySelectorAll(".chat-date-separator[data-date-key]");
  dateSeparators.forEach(sep => {
    const dateKey = sep.getAttribute("data-date-key");
    const bubble = sep.querySelector(".chat-date-bubble");
    if (dateKey && bubble) {
      const currentLabel = getRelativeDateLabel(dateKey);
      if (bubble.textContent !== currentLabel) {
        bubble.textContent = currentLabel;
      }
    }
  });
}, 15000);

// Start App
init();
