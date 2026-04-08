/**
 * AI Agent Chat Widget - Plug & Play
 *
 * Usage: Add this to ANY website:
 *   <script src="http://YOUR_SERVER:8000/widget/ai-agent-widget.js"></script>
 *   <script>
 *     AIAgent.init({ server: "http://YOUR_SERVER:8000" });
 *   </script>
 */

(function () {
  "use strict";

  const DEFAULT_CONFIG = {
    server: "http://localhost:8000",
    position: "bottom-right",    // bottom-right, bottom-left
    title: "AI Assistant",
    subtitle: "Ask me anything about your data",
    placeholder: "Type your question...",
    theme: "#4F46E5",            // Primary color
    width: "380px",
    height: "520px",
    projectKey: "",              // Project key from dashboard
    apiKey: "",                  // API key from dashboard
    sessionId: "",               // Auto-generated if empty
    welcome: "Hello! I'm your AI assistant. I can answer questions about your data, run queries, and give suggestions. How can I help?",
  };

  let config = { ...DEFAULT_CONFIG };
  let isOpen = false;
  let sessionId = "";

  function generateId() {
    return "session_" + Math.random().toString(36).substring(2, 10);
  }

  function createStyles() {
    const style = document.createElement("style");
    style.textContent = `
      #ai-agent-widget-container * {
        box-sizing: border-box;
        margin: 0;
        padding: 0;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      }

      #ai-agent-fab {
        position: fixed;
        ${config.position === "bottom-left" ? "left: 20px" : "right: 20px"};
        bottom: 20px;
        width: 56px;
        height: 56px;
        border-radius: 50%;
        background: ${config.theme};
        color: white;
        border: none;
        cursor: pointer;
        box-shadow: 0 4px 12px rgba(0,0,0,0.25);
        z-index: 99999;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: transform 0.2s, box-shadow 0.2s;
      }

      #ai-agent-fab:hover {
        transform: scale(1.08);
        box-shadow: 0 6px 20px rgba(0,0,0,0.3);
      }

      #ai-agent-fab svg {
        width: 26px;
        height: 26px;
        fill: white;
      }

      #ai-agent-chat {
        position: fixed;
        ${config.position === "bottom-left" ? "left: 20px" : "right: 20px"};
        bottom: 88px;
        width: ${config.width};
        height: ${config.height};
        background: #fff;
        border-radius: 16px;
        box-shadow: 0 8px 40px rgba(0,0,0,0.2);
        z-index: 99999;
        display: none;
        flex-direction: column;
        overflow: hidden;
      }

      #ai-agent-chat.open {
        display: flex;
      }

      #ai-agent-header {
        background: ${config.theme};
        color: white;
        padding: 16px;
        display: flex;
        align-items: center;
        justify-content: space-between;
      }

      #ai-agent-header-info h3 {
        font-size: 15px;
        font-weight: 600;
      }

      #ai-agent-header-info p {
        font-size: 11px;
        opacity: 0.85;
        margin-top: 2px;
      }

      #ai-agent-status {
        display: flex;
        align-items: center;
        gap: 5px;
        font-size: 11px;
        opacity: 0.9;
        margin-top: 4px;
      }

      #ai-agent-status-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: #4ade80;
      }

      #ai-agent-close {
        background: none;
        border: none;
        color: white;
        cursor: pointer;
        font-size: 20px;
        padding: 4px;
        line-height: 1;
        opacity: 0.8;
      }

      #ai-agent-close:hover {
        opacity: 1;
      }

      #ai-agent-messages {
        flex: 1;
        overflow-y: auto;
        padding: 16px;
        display: flex;
        flex-direction: column;
        gap: 12px;
        background: #f9fafb;
      }

      .ai-msg {
        max-width: 85%;
        padding: 14px 18px !important;
        border-radius: 14px;
        font-size: 13px;
        line-height: 1.6;
        word-wrap: break-word;
      }

      .ai-msg-user {
        align-self: flex-end;
        background: ${config.theme};
        color: white;
        padding: 12px 20px !important;
        border-radius: 14px;
        border-bottom-right-radius: 4px;
      }

      .ai-msg-agent {
        align-self: flex-start;
        background: white;
        color: #1f2937;
        border: 1px solid #e5e7eb;
        border-bottom-left-radius: 4px;
      }

      .ai-msg-suggestions {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-top: 8px;
      }

      .ai-suggestion-btn {
        background: #f3f4f6;
        border: 1px solid #e5e7eb;
        border-radius: 16px;
        padding: 4px 10px;
        font-size: 11px;
        color: #4b5563;
        cursor: pointer;
        transition: background 0.15s;
      }

      .ai-suggestion-btn:hover {
        background: #e5e7eb;
      }

      .ai-typing {
        align-self: flex-start;
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        padding: 10px 14px;
        display: none;
      }

      .ai-typing-dots {
        display: flex;
        gap: 4px;
      }

      .ai-typing-dots span {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: #9ca3af;
        animation: aiTyping 1.2s infinite;
      }

      .ai-typing-dots span:nth-child(2) { animation-delay: 0.2s; }
      .ai-typing-dots span:nth-child(3) { animation-delay: 0.4s; }

      @keyframes aiTyping {
        0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
        30% { transform: translateY(-4px); opacity: 1; }
      }

      #ai-agent-input-area {
        display: flex;
        padding: 12px;
        gap: 8px;
        background: white;
        border-top: 1px solid #e5e7eb;
      }

      #ai-agent-input {
        flex: 1;
        border: 1px solid #d1d5db;
        border-radius: 20px;
        padding: 8px 16px;
        font-size: 13px;
        outline: none;
        transition: border-color 0.15s;
      }

      #ai-agent-input:focus {
        border-color: ${config.theme};
      }

      #ai-agent-send {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        background: ${config.theme};
        color: white;
        border: none;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: opacity 0.15s;
      }

      #ai-agent-send:hover {
        opacity: 0.9;
      }

      #ai-agent-send:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }

      #ai-agent-send svg {
        width: 16px;
        height: 16px;
        fill: white;
      }

      #ai-agent-powered {
        text-align: center;
        font-size: 10px;
        color: #9ca3af;
        padding: 4px;
        background: white;
      }

      @media (max-width: 480px) {
        #ai-agent-chat {
          width: calc(100vw - 16px);
          height: calc(100vh - 100px);
          right: 8px;
          left: 8px;
          bottom: 80px;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function createWidget() {
    const container = document.createElement("div");
    container.id = "ai-agent-widget-container";

    container.innerHTML = `
      <button id="ai-agent-fab" aria-label="Open AI Assistant">
        <svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/></svg>
      </button>

      <div id="ai-agent-chat">
        <div id="ai-agent-header">
          <div id="ai-agent-header-info">
            <h3>${config.title}</h3>
            <p>${config.subtitle}</p>
            <div id="ai-agent-status">
              <span id="ai-agent-status-dot"></span>
              <span id="ai-agent-status-text">Online</span>
            </div>
          </div>
          <button id="ai-agent-close">&times;</button>
        </div>

        <div id="ai-agent-messages">
          <div class="ai-typing" id="ai-agent-typing">
            <div class="ai-typing-dots">
              <span></span><span></span><span></span>
            </div>
          </div>
        </div>

        <div id="ai-agent-input-area">
          <input type="text" id="ai-agent-input" placeholder="${config.placeholder}" autocomplete="off" />
          <button id="ai-agent-send">
            <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
          </button>
        </div>

        <div id="ai-agent-powered">Powered by AI Agent Engine</div>
      </div>
    `;

    document.body.appendChild(container);
  }

  function formatMarkdown(text) {
    if (!text) return "";
    return text
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.*?)\*/g, "<em>$1</em>")
      .replace(/`(.*?)`/g, "<code style='background:#f3f4f6;padding:1px 4px;border-radius:3px;font-size:12px'>$1</code>")
      .replace(/\n- /g, "\n&bull; ")
      .replace(/\n\d+\.\s/g, function(m) { return "\n" + m.trim() + " "; })
      .replace(/\n/g, "<br>");
  }

  function buildDataTable(data) {
    if (!data || !data.length) return "";
    var keys = Object.keys(data[0]);
    var html = '<div style="overflow-x:auto;margin-top:8px">';
    html += '<table style="width:100%;border-collapse:collapse;font-size:11px">';
    html += '<thead><tr>';
    keys.forEach(function(k) {
      html += '<th style="text-align:left;padding:4px 8px;background:#f3f4f6;border-bottom:2px solid #e5e7eb;font-size:10px;color:#6b7280;white-space:nowrap">' + k + '</th>';
    });
    html += '</tr></thead><tbody>';
    data.slice(0, 20).forEach(function(row) {
      html += '<tr>';
      keys.forEach(function(k) {
        var val = row[k];
        if (val === null || val === undefined) val = "-";
        if (typeof val === "object") val = JSON.stringify(val);
        var display = String(val).length > 30 ? String(val).substring(0, 30) + "..." : String(val);
        html += '<td style="padding:4px 8px;border-bottom:1px solid #f3f4f6;white-space:nowrap">' + display + '</td>';
      });
      html += '</tr>';
    });
    html += '</tbody></table>';
    if (data.length > 20) html += '<div style="font-size:10px;color:#9ca3af;padding:4px">Showing 20 of ' + data.length + ' rows</div>';
    html += '</div>';
    return html;
  }

  function addMessage(text, type, suggestions, data) {
    var messages = document.getElementById("ai-agent-messages");
    var typing = document.getElementById("ai-agent-typing");

    var msg = document.createElement("div");
    msg.className = "ai-msg ai-msg-" + type;

    if (type === "agent") {
      msg.innerHTML = formatMarkdown(text);
      if (data && data.length) {
        msg.innerHTML += buildDataTable(data);
      }
    } else {
      msg.textContent = text;
    }

    if (suggestions && suggestions.length > 0 && type === "agent") {
      var sugDiv = document.createElement("div");
      sugDiv.className = "ai-msg-suggestions";
      suggestions.forEach(function (s) {
        var btn = document.createElement("button");
        btn.className = "ai-suggestion-btn";
        btn.textContent = s;
        btn.onclick = function () {
          sendMessage(s);
        };
        sugDiv.appendChild(btn);
      });
      msg.appendChild(sugDiv);
    }

    messages.insertBefore(msg, typing);
    messages.scrollTop = messages.scrollHeight;
  }

  var _typingInterval = null;
  var _typingStages = [
    "Understanding your question",
    "Searching database",
    "Analyzing data",
    "Preparing answer"
  ];

  function showTyping(show) {
    var typing = document.getElementById("ai-agent-typing");
    if (show) {
      typing.style.display = "block";
      var stageIdx = 0;
      var typingText = typing.querySelector(".ai-typing-text");
      if (!typingText) {
        typingText = document.createElement("div");
        typingText.className = "ai-typing-text";
        typingText.style.cssText = "font-size:11px;color:#6b7280;margin-top:4px";
        typing.appendChild(typingText);
      }
      typingText.textContent = _typingStages[0] + "...";
      _typingInterval = setInterval(function() {
        stageIdx++;
        if (stageIdx < _typingStages.length) {
          typingText.textContent = _typingStages[stageIdx] + "...";
        }
      }, 1500);
      var messages = document.getElementById("ai-agent-messages");
      messages.scrollTop = messages.scrollHeight;
    } else {
      typing.style.display = "none";
      if (_typingInterval) {
        clearInterval(_typingInterval);
        _typingInterval = null;
      }
    }
  }

  function sendMessage(text) {
    if (!text || !text.trim()) return;

    var input = document.getElementById("ai-agent-input");
    var sendBtn = document.getElementById("ai-agent-send");
    input.value = "";

    addMessage(text, "user");
    showTyping(true);
    sendBtn.disabled = true;

    var headers = { "Content-Type": "application/json" };
    if (config.projectKey) {
      headers["X-Project-Key"] = config.projectKey;
    }
    if (config.apiKey) {
      headers["X-API-Key"] = config.apiKey;
    }

    var controller = new AbortController();
    var timeoutId = setTimeout(function() { controller.abort(); }, 120000);

    fetch(config.server + "/api/ask", {
      method: "POST",
      headers: headers,
      body: JSON.stringify({
        question: text,
        session_id: sessionId,
      }),
      signal: controller.signal,
    })
      .then(function (res) {
        clearTimeout(timeoutId);
        if (!res.ok) {
          return res.json().then(function(err) { throw new Error(err.detail || "Server error"); });
        }
        return res.json();
      })
      .then(function (data) {
        showTyping(false);
        sendBtn.disabled = false;
        addMessage(
          data.answer || "I couldn't process that request.",
          "agent",
          data.suggestions || [],
          data.data || null
        );
      })
      .catch(function (err) {
        clearTimeout(timeoutId);
        showTyping(false);
        sendBtn.disabled = false;
        if (err.name === 'AbortError') {
          addMessage("Response took too long. The AI model might be loading. Please try again.", "agent");
        } else {
          addMessage("Error: " + err.message, "agent");
        }
      });
  }

  function bindEvents() {
    var fab = document.getElementById("ai-agent-fab");
    var chat = document.getElementById("ai-agent-chat");
    var closeBtn = document.getElementById("ai-agent-close");
    var input = document.getElementById("ai-agent-input");
    var sendBtn = document.getElementById("ai-agent-send");

    fab.onclick = function () {
      isOpen = !isOpen;
      if (isOpen) {
        chat.classList.add("open");
        fab.innerHTML = '<svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>';
        input.focus();
      } else {
        chat.classList.remove("open");
        fab.innerHTML = '<svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/></svg>';
      }
    };

    closeBtn.onclick = function () {
      isOpen = false;
      chat.classList.remove("open");
      fab.innerHTML = '<svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/></svg>';
    };

    sendBtn.onclick = function () {
      sendMessage(input.value);
    };

    input.onkeydown = function (e) {
      if (e.key === "Enter") {
        sendMessage(input.value);
      }
    };
  }

  function checkConnection() {
    fetch(config.server + "/api/health")
      .then(function (res) { return res.json(); })
      .then(function (data) {
        var dot = document.getElementById("ai-agent-status-dot");
        var text = document.getElementById("ai-agent-status-text");
        if (data.database_connected) {
          dot.style.background = "#4ade80";
          text.textContent = "Online - " + (data.domain || data.db_type || "Connected");
        } else {
          dot.style.background = "#fbbf24";
          text.textContent = "Online - No database connected";
        }
      })
      .catch(function () {
        var dot = document.getElementById("ai-agent-status-dot");
        var text = document.getElementById("ai-agent-status-text");
        dot.style.background = "#ef4444";
        text.textContent = "Offline";
      });
  }

  // Public API
  window.AIAgent = {
    init: function (userConfig) {
      config = Object.assign({}, DEFAULT_CONFIG, userConfig || {});
      sessionId = config.sessionId || generateId();

      if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
          createStyles();
          createWidget();
          bindEvents();
          addMessage(config.welcome, "agent");
          checkConnection();
        });
      } else {
        createStyles();
        createWidget();
        bindEvents();
        addMessage(config.welcome, "agent");
        checkConnection();
      }
    },

    open: function () {
      if (!isOpen) document.getElementById("ai-agent-fab").click();
    },

    close: function () {
      if (isOpen) document.getElementById("ai-agent-fab").click();
    },

    send: function (text) {
      sendMessage(text);
    },

    setConfig: function (newConfig) {
      config = Object.assign(config, newConfig);
    },
  };
})();
